"""
Real-time trading dashboard API with WebSocket support.

Provides:
- Live position and P&L updates
- Trade history streaming
- Natural language command parsing
- Market alerts and notifications
"""

import sys
from pathlib import Path

# Run as `python src/dashboard_api.py`: make the repo root (providers/), the
# agents package, and src/ importable regardless of the working directory.
_ROOT = Path(__file__).resolve().parents[1]
for _path in (_ROOT, _ROOT / "agents", _ROOT / "src"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import asyncio
import json
import random
from collections import deque
from datetime import datetime
import logging
import re

# Trading system imports
from augur_agents.trading.pipeline import TradingPipeline
from augur_agents.trading.journal import TradeJournal
from augur_agents.trading.monitor import PositionMonitor
from config import Settings, load_settings
from augur_agents.trading.markets import UNIVERSE, snapshot_from_bars
from providers import fred
from providers.base import DataUnavailable, OrderSide
from providers.market_data import AlpacaMarketData
from providers.stocks_alpaca import AlpacaProvider
from technical_indicators import TechnicalIndicators, SignalDetector
import integrations

logger = logging.getLogger(__name__)

# ============================================================================
# Data Models for API
# ============================================================================

class Position(BaseModel):
    """Active position snapshot"""
    symbol: str
    quantity: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    unrealized_pnl_pct: float
    side: str  # BUY or SELL
    thesis_valid: bool
    stop_price: Optional[float] = None
    target_price: Optional[float] = None


class Trade(BaseModel):
    """Completed trade record"""
    trade_id: str
    symbol: str
    entry_price: float
    exit_price: float
    quantity: float
    side: str
    pnl: float
    pnl_pct: float
    entry_time: str
    exit_time: str
    thesis_status: str  # "thesis_invalidated", "hit_target", "hit_stop", etc.
    analysis_tags: List[str]  # "good_execution", "aligned_signals", etc.


class EquityPoint(BaseModel):
    t: str
    equity: float


class PortfolioDashboard(BaseModel):
    """Complete portfolio snapshot"""
    account_equity: float
    cash: float
    buying_power: float
    total_pnl: float
    total_pnl_pct: float
    max_drawdown: float
    positions: List[Position]
    recent_trades: List[Trade]
    timestamp: str
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    mode: str = "demo"
    halted: bool = False
    equity_curve: List[EquityPoint] = []


class CommandRequest(BaseModel):
    """Natural language command from chat"""
    text: str
    symbol: Optional[str] = None


class CommandResponse(BaseModel):
    """Response to natural language command"""
    understood: bool
    action: Optional[str] = None  # "CLOSE_POSITION", "ADJUST_SIZE", "MANUAL_OVERRIDE", etc.
    params: Optional[Dict[str, Any]] = None
    reasoning: str
    risk_warning: Optional[str] = None
    requires_confirmation: bool = True


class Alert(BaseModel):
    """Market or trading alert"""
    alert_type: str  # "NEWS", "POSITION_ALERT", "RISK_WARNING", "EXECUTION_FAILURE"
    symbol: Optional[str] = None
    message: str
    severity: str  # "INFO", "WARNING", "CRITICAL"
    timestamp: str


class Indicators(BaseModel):
    """Technical indicators for a symbol"""
    symbol: str
    rsi: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_histogram: Optional[float] = None
    ma_50: Optional[float] = None
    ma_100: Optional[float] = None
    ma_200: Optional[float] = None
    entry_signal: Optional[str] = None  # "BUY" or None
    entry_strength: int = 0  # 0-100
    exit_signal: Optional[str] = None  # "SELL" or None
    exit_strength: int = 0  # 0-100
    trend: str = "NEUTRAL"  # "UPTREND", "DOWNTREND", "NEUTRAL"


class SignalData(BaseModel):
    """Signal data with reasons"""
    signal: Optional[str] = None
    strength: int
    reasons: List[str]


# ============================================================================
# FastAPI App Setup
# ============================================================================

app = FastAPI(
    title="Augur Trading Dashboard API",
    description="Real-time dashboard for multi-agent trading system",
    version="1.0.0"
)

# Enable CORS for the local frontend. Origins must include a scheme and port
# (e.g. the Vite dev server at http://localhost:5173); bare hostnames never match.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# Trading State Management
# ============================================================================

class TradingState:
    """Thread-safe state holder for trading system.

    Accounting: equity = baseline + realized P&L + unrealized P&L, and cash is
    what equity leaves after the net market value of open positions (a cash
    account: longs consume cash, short proceeds add to it). In demo mode prices
    are simulated; once real broker positions are loaded they never are.
    """

    def __init__(self, settings: Optional[Settings] = None, *, connect_broker: bool = True):
        # load_settings() enforces the live-trading safety check; Settings() alone skips it.
        self.settings = settings or load_settings()
        self.pipeline = TradingPipeline()
        self.journal = TradeJournal()
        self.monitor = PositionMonitor()

        # Initialize Alpaca provider for real account data
        self.alpaca: Optional[AlpacaProvider] = None
        if connect_broker:
            try:
                self.alpaca = AlpacaProvider(self.settings)
                logger.info("Alpaca provider initialized successfully")
            except Exception as e:
                logger.warning(f"Could not initialize Alpaca: {e}. Using demo mode.")

        # True until real broker positions are loaded; gates price simulation
        # and whether closes are sent to the broker.
        self.demo_mode = True

        # State tracking
        self.initial_equity = self.settings.initial_capital
        self.account_equity = self.initial_equity
        self.realized_pnl = 0.0
        self.equity_history: List[float] = [self.initial_equity]
        # Timestamped copy for charts, bounded so a long session can't grow it forever.
        self.equity_points: deque = deque([(datetime.now().isoformat(), self.initial_equity)], maxlen=720)
        self.positions: Dict[str, Dict[str, Any]] = {}  # symbol -> position data
        self.trades: List[Dict[str, Any]] = []  # All completed trades
        self.price_history: Dict[str, List[float]] = {}  # symbol -> price history (last 100 points)
        self.indicators: Dict[str, Dict[str, Any]] = {}  # symbol -> current indicators
        self.lock = asyncio.Lock()
        self.last_update = datetime.now()

    @property
    def halted(self) -> bool:
        return self.pipeline.guard.halted

    async def add_position(
        self,
        symbol: str,
        quantity: float,
        entry_price: float,
        side: str,
        thesis: str = "",
        current_price: Optional[float] = None,
    ):
        """Add new position"""
        async with self.lock:
            self.positions[symbol] = {
                'symbol': symbol,
                'quantity': quantity,
                'entry_price': entry_price,
                'current_price': entry_price,
                'side': side,
                'pnl': 0.0,
                'pnl_pct': 0.0,
                'thesis_valid': True,
                'thesis': thesis,
                'stop_price': None,
                'target_price': None,
                'entry_time': datetime.now().isoformat(),
            }
            self._mark(symbol, current_price if current_price is not None else entry_price)
            logger.info(f"Added position: {symbol} {quantity} @ {entry_price}")

    def _mark(self, symbol: str, current_price: float):
        """Apply a new price to a position. Caller must hold the lock."""
        pos = self.positions[symbol]
        pos['current_price'] = current_price
        if pos['side'] == 'BUY':
            pos['pnl'] = (current_price - pos['entry_price']) * pos['quantity']
        else:  # SELL
            pos['pnl'] = (pos['entry_price'] - current_price) * pos['quantity']
        cost = pos['entry_price'] * pos['quantity']
        pos['pnl_pct'] = (pos['pnl'] / cost) * 100 if cost > 0 else 0.0

        self.update_price_history(symbol, current_price)
        self.calculate_indicators(symbol)
        self._calculate_account_equity()

    async def update_position_price(self, symbol: str, current_price: float):
        """Update position current price and P&L"""
        async with self.lock:
            if symbol in self.positions:
                self._mark(symbol, current_price)

    def unrealized_pnl(self) -> float:
        return sum(pos['pnl'] for pos in self.positions.values())

    def net_position_value(self) -> float:
        """Long market value minus short market value."""
        return sum(
            pos['quantity'] * pos['current_price'] * (1 if pos['side'] == 'BUY' else -1)
            for pos in self.positions.values()
        )

    def cash(self) -> float:
        return self.account_equity - self.net_position_value()

    def _calculate_account_equity(self):
        """Equity = baseline capital + realized P&L + open P&L."""
        new_equity = self.initial_equity + self.realized_pnl + self.unrealized_pnl()

        # Only update history if equity changed significantly
        if not self.equity_history or abs(new_equity - self.equity_history[-1]) > 0.01:
            self.equity_history.append(new_equity)
            self.equity_points.append((datetime.now().isoformat(), new_equity))

        self.account_equity = new_equity

    async def close_position(self, symbol: str, exit_price: float, reason: str = "manual_close") -> Dict[str, Any]:
        """Close a position"""
        async with self.lock:
            return self._close_position_locked(symbol, exit_price, reason)

    def _close_position_locked(
        self, symbol: str, exit_price: float, reason: str, *, send_to_broker: bool = True
    ) -> Dict[str, Any]:
        """Close a position. Caller must hold the lock (asyncio.Lock is not reentrant)."""
        if symbol not in self.positions:
            return {"success": False, "error": f"No position for {symbol}"}

        pos = self.positions[symbol]

        # Live positions close at the broker first; local state only follows a real close.
        if send_to_broker and not self.demo_mode and self.alpaca is not None:
            result = self.alpaca.close_position(symbol)
            if result.status == "REJECTED":
                logger.error(f"Broker rejected close for {symbol}: {result.raw_error}")
                return {"success": False, "error": f"Broker rejected close: {result.raw_error}"}
            if result.avg_fill_price:
                exit_price = result.avg_fill_price

        # Record in journal
        trade_record = {
            'symbol': symbol,
            'entry': pos['entry_price'],
            'exit': exit_price,
            'size': pos['quantity'],
            'side': pos['side'],
            'thesis': pos.get('thesis', ''),
        }
        journal_entry = self.journal.record_trade(trade_record, provenance={"close_reason": reason})
        cost = pos['entry_price'] * pos['quantity']

        # Add to trades list
        trade_data = {
            'trade_id': journal_entry['trade_id'],
            'symbol': symbol,
            'entry_price': pos['entry_price'],
            'exit_price': exit_price,
            'quantity': pos['quantity'],
            'side': pos['side'],
            'pnl': journal_entry['pnl'],
            'pnl_pct': (journal_entry['pnl'] / cost) * 100 if cost > 0 else 0.0,
            'entry_time': pos['entry_time'],
            'exit_time': datetime.now().isoformat(),
            'thesis_status': reason,
            'analysis_tags': [],
        }
        self.trades.append(trade_data)

        # Realize the P&L, drop the position, then recompute equity from the ledger.
        self.realized_pnl += journal_entry['pnl']
        del self.positions[symbol]
        self._calculate_account_equity()

        logger.info(f"Closed position: {symbol} P&L: ${journal_entry['pnl']:.2f}")
        return {
            "success": True,
            "pnl": journal_entry['pnl'],
            "trade_id": journal_entry['trade_id']
        }

    async def kill_switch(self, reason: str) -> Dict[str, Any]:
        """Halt new entries and flatten everything, at the broker when live."""
        self.pipeline.guard.halt(reason)
        async with self.lock:
            broker_results = []
            if not self.demo_mode and self.alpaca is not None:
                broker_results = [r.status for r in self.alpaca.close_all_positions()]
            # One broker-wide flatten above; the local closes only record it.
            closed = [
                self._close_position_locked(
                    symbol, pos['current_price'], f"kill_switch: {reason}", send_to_broker=False
                )
                for symbol, pos in list(self.positions.items())
            ]
        logger.critical(f"Kill switch tripped: {reason}")
        return {"halted": True, "reason": reason, "closed": len(closed), "broker_results": broker_results}

    def get_max_drawdown(self) -> float:
        """Calculate max drawdown from equity history"""
        if not self.equity_history:
            return 0.0

        peak = self.equity_history[0]
        max_dd = 0.0

        for equity in self.equity_history:
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak if peak > 0 else 0.0
            max_dd = max(max_dd, dd)

        return max_dd * 100

    def update_price_history(self, symbol: str, price: float):
        """Track price history for indicator calculations (keep last 100 points)"""
        if symbol not in self.price_history:
            self.price_history[symbol] = []
        
        self.price_history[symbol].append(price)
        # Keep only last 100 prices for efficiency
        if len(self.price_history[symbol]) > 100:
            self.price_history[symbol] = self.price_history[symbol][-100:]
    
    def calculate_indicators(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Calculate technical indicators for a symbol"""
        if symbol not in self.price_history or len(self.price_history[symbol]) < 30:
            return None
        
        try:
            prices = self.price_history[symbol]
            
            # Calculate indicators
            rsi = TechnicalIndicators.compute_rsi(prices, 14)
            macd_line, signal_line, histogram = TechnicalIndicators.compute_macd(prices, 12, 26, 9)
            ma_50 = TechnicalIndicators.compute_sma(prices, 50)
            ma_100 = TechnicalIndicators.compute_sma(prices, 100)
            ma_200 = TechnicalIndicators.compute_sma(prices, 200)
            
            # Get current values
            current_rsi = rsi[-1] if rsi[-1] is not None else None
            current_macd = macd_line[-1] if macd_line[-1] is not None else None
            current_signal = signal_line[-1] if signal_line[-1] is not None else None
            current_histogram = histogram[-1] if histogram[-1] is not None else None
            current_ma50 = ma_50[-1] if ma_50[-1] is not None else None
            current_ma100 = ma_100[-1] if ma_100[-1] is not None else None
            current_ma200 = ma_200[-1] if ma_200[-1] is not None else None
            
            # Detect entry/exit signals
            entry_signal = SignalDetector.detect_entry_signals(prices, rsi, macd_line, signal_line, ma_50, ma_100, ma_200)
            exit_signal = SignalDetector.detect_exit_signals(prices, rsi, macd_line, signal_line)
            
            # Determine trend
            if current_ma50 and current_ma100 and current_ma200:
                if current_ma50 > current_ma100 > current_ma200:
                    trend = "UPTREND"
                elif current_ma50 < current_ma100 < current_ma200:
                    trend = "DOWNTREND"
                else:
                    trend = "NEUTRAL"
            else:
                trend = "NEUTRAL"
            
            indicators = {
                "symbol": symbol,
                "rsi": current_rsi,
                "macd": current_macd,
                "macd_signal": current_signal,
                "macd_histogram": current_histogram,
                "ma_50": current_ma50,
                "ma_100": current_ma100,
                "ma_200": current_ma200,
                "entry_signal": entry_signal.get("signal"),
                "entry_strength": entry_signal.get("strength", 0),
                "entry_reasons": entry_signal.get("reasons", []),
                "exit_signal": exit_signal.get("signal"),
                "exit_strength": exit_signal.get("strength", 0),
                "exit_reasons": exit_signal.get("reasons", []),
                "trend": trend,
            }
            
            self.indicators[symbol] = indicators
            return indicators
        
        except Exception as e:
            logger.error(f"Error calculating indicators for {symbol}: {e}")
            return None
    
    
    async def load_alpaca_positions(self) -> bool:
        """Load real positions from Alpaca with their real entry and mark prices."""
        if not self.alpaca:
            logger.info("Alpaca not available, using demo mode")
            return False

        try:
            account = self.alpaca.get_account()
            broker_positions = self.alpaca.get_positions()
        except Exception as e:
            logger.error(f"Failed to load Alpaca positions: {e}")
            return False

        logger.info(f"Loaded Alpaca account: equity=${account.equity:.2f}, cash=${account.cash:.2f}")
        if not broker_positions:
            logger.info("No positions in Alpaca account, using demo mode")
            return False

        missing = [p.symbol for p in broker_positions if not p.avg_entry_price or not p.current_price]
        if missing:
            # Never substitute a placeholder price: P&L and risk would be fiction.
            logger.error(f"Alpaca positions without entry/mark prices: {missing}; staying in demo mode")
            return False

        logger.info(f"Loading {len(broker_positions)} positions from Alpaca")
        async with self.lock:
            self.positions.clear()
            self.realized_pnl = 0.0
        for p in broker_positions:
            assert p.avg_entry_price is not None  # filtered above
            side = "BUY" if p.side == OrderSide.BUY else "SELL"
            await self.add_position(
                p.symbol, p.quantity, p.avg_entry_price, side, "Imported from Alpaca",
                current_price=p.current_price,
            )

        async with self.lock:
            # Broker equity already includes open P&L; back it out of the baseline
            # so equity = baseline + realized + unrealized reproduces it exactly.
            self.initial_equity = account.equity - self.unrealized_pnl()
            self.equity_history = [account.equity]
            self.equity_points = deque([(datetime.now().isoformat(), account.equity)], maxlen=720)
            self._calculate_account_equity()
            self.demo_mode = False
        return True

# Initialize trading state
trading_state = TradingState()

# ============================================================================
# Connection Management
# ============================================================================

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.alerts: asyncio.Queue = asyncio.Queue()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Client connected. Active connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        # Idempotent: a failed broadcast and the receive loop may both disconnect the same socket.
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"Client disconnected. Active connections: {len(self.active_connections)}")

    async def broadcast(self, message: Dict[str, Any]):
        """Send message to all connected clients"""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to connection: {e}")
                disconnected.append(connection)
        
        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn)

    async def broadcast_alert(self, alert: Alert):
        """Send alert to all clients"""
        await self.broadcast({
            "type": "alert",
            "data": alert.model_dump()
        })


manager = ConnectionManager()

# ============================================================================
# WebSocket Endpoints
# ============================================================================

@app.websocket("/ws/dashboard")
async def websocket_dashboard(websocket: WebSocket):
    """
    Main dashboard WebSocket connection.
    Sends real-time position updates, P&L, trade alerts.
    """
    await manager.connect(websocket)
    try:
        while True:
            # Receive commands from client (chat, manual actions, etc.)
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message["type"] == "command":
                await handle_command(websocket, message["data"])
            elif message["type"] == "action":
                await handle_action(websocket, message["data"])
            
            # Broadcast current portfolio state
            portfolio = await get_portfolio_snapshot()
            await manager.broadcast({
                "type": "portfolio_update",
                "data": portfolio.model_dump()
            })
            
            # Broadcast alerts
            while not manager.alerts.empty():
                alert = manager.alerts.get_nowait()
                await manager.broadcast({
                    "type": "alert",
                    "data": alert
                })
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("Client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


# ============================================================================
# REST Endpoints
# ============================================================================

@app.get("/api/portfolio", response_model=PortfolioDashboard)
async def get_portfolio():
    """Get current portfolio snapshot"""
    return await get_portfolio_snapshot()


@app.get("/api/positions", response_model=List[Position])
async def get_positions():
    """Get all active positions"""
    portfolio = await get_portfolio_snapshot()
    return portfolio.positions


@app.get("/api/trades", response_model=List[Trade])
async def get_trades(limit: int = 50):
    """Get recent trade history"""
    portfolio = await get_portfolio_snapshot()
    return portfolio.recent_trades[-limit:]


@app.get("/api/indicators")
async def get_indicators():
    """Get technical indicators for all positions"""
    indicators_list = []
    for symbol in trading_state.positions.keys():
        if symbol in trading_state.indicators:
            indicators_list.append(trading_state.indicators[symbol])
    return {"indicators": indicators_list}


@app.post("/api/command", response_model=CommandResponse)
async def process_command(cmd: CommandRequest):
    """
    Process natural language command via chat.
    Examples:
    - "sell AAPL at $150 stop"
    - "close position if earnings miss"
    - "increase size by 50 shares"
    """
    return await parse_and_validate_command(cmd.text, cmd.symbol)


@app.post("/api/action")
async def execute_action(action: Dict[str, Any]):
    """
    Execute manual action (sell, close, adjust size, etc.)
    Requires explicit confirmation for risk-sensitive actions.
    """
    action_type = action.get("type")
    symbol = action.get("symbol")
    params = action.get("params", {})
    
    if not symbol:
        raise HTTPException(status_code=400, detail="Symbol required")
    
    if action_type == "CLOSE_POSITION":
        # Close position at market price
        result = await trading_state.close_position(
            symbol,
            trading_state.positions[symbol]['current_price'] if symbol in trading_state.positions else 0,
            reason="manual_close"
        )
        
        if result["success"]:
            # Broadcast alert
            await manager.broadcast_alert(Alert(
                alert_type="POSITION_ALERT",
                symbol=symbol,
                message=f"Position closed: ${result.get('pnl', 0):.2f} P&L",
                severity="INFO",
                timestamp=datetime.now().isoformat()
            ))
        
        return result
    
    elif action_type == "ADJUST_SIZE":
        return await adjust_position_size(symbol, params.get("quantity"))

    elif action_type == "MANUAL_OVERRIDE":
        # Never report an order that was not placed.
        raise HTTPException(
            status_code=501,
            detail="Manual overrides are not implemented; nothing was executed",
        )

    elif action_type == "UPDATE_STOP":
        return await update_stop(symbol, params.get("stop_price"))
    
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action_type}")


class IntegrationKeys(BaseModel):
    values: Dict[str, str]


@app.get("/api/integrations")
async def list_integrations():
    """Which services are connected. Key values are never included."""
    settings = trading_state.settings
    return {
        "integrations": integrations.status(settings),
        "trading_mode": settings.trading_mode.value,
        "env_file_exists": integrations.ENV_FILE.exists(),
    }


@app.post("/api/integrations/{integration_id}/keys")
async def save_integration_keys(integration_id: str, body: IntegrationKeys):
    """Save keys for one integration to .env. Paper/testnet flags cannot be changed here."""
    integration = integrations.BY_ID.get(integration_id)
    if integration is None:
        raise HTTPException(status_code=404, detail=f"Unknown integration {integration_id}")
    unknown = set(body.values) - set(integration.env_vars)
    if unknown:
        raise HTTPException(status_code=400, detail=f"{integration.name} does not use {sorted(unknown)}")
    cleaned = {name: value.strip() for name, value in body.values.items() if value and value.strip()}
    if any(("\n" in v or "\r" in v or " " in v) for v in cleaned.values()):
        raise HTTPException(status_code=400, detail="Keys can't contain spaces or line breaks")
    if not cleaned:
        raise HTTPException(status_code=400, detail="Paste at least one key")

    integrations.write_env(cleaned)
    trading_state.settings = load_settings()
    if integration_id == "alpaca":
        try:
            trading_state.alpaca = AlpacaProvider(trading_state.settings)
        except Exception as e:
            trading_state.alpaca = None
            logger.warning(f"Alpaca keys saved but client could not start: {e}")
    return {"saved": sorted(cleaned), "integration": next(
        row for row in integrations.status(trading_state.settings) if row["id"] == integration_id
    )}


@app.post("/api/integrations/{integration_id}/test")
async def test_integration(integration_id: str):
    """Try a real, read-only call with the saved keys and say plainly what happened."""
    integration = integrations.BY_ID.get(integration_id)
    if integration is None:
        raise HTTPException(status_code=404, detail=f"Unknown integration {integration_id}")
    row = next(r for r in integrations.status(trading_state.settings) if r["id"] == integration_id)
    if not row["configured"]:
        return {"ok": False, "message": f"Add your {integration.name} keys first."}

    if integration_id == "alpaca":
        try:
            account = await asyncio.to_thread(lambda: AlpacaProvider(trading_state.settings).get_account())
        except Exception as e:
            return {"ok": False, "message": f"Alpaca said no: {e}. Check that both keys are pasted correctly."}
        mode = "practice money" if trading_state.settings.alpaca_paper else "REAL money"
        return {"ok": True, "message": f"Connected! Account has ${account.equity:,.2f} ({mode})."}

    if integration_id == "binance":
        try:
            from providers.crypto_binance import BinanceProvider
        except ImportError:
            return {"ok": False, "message": "Keys saved. Install the Binance library first: pip install python-binance"}
        try:
            account = await asyncio.to_thread(lambda: BinanceProvider(trading_state.settings).get_account())
        except Exception as e:
            return {"ok": False, "message": f"Binance said no: {e}. Check that both keys are pasted correctly."}
        return {"ok": True, "message": f"Connected! Testnet wallet worth ${account.equity:,.2f}."}

    return {"ok": True, "message": f"{integration.name} key is saved. It will be used when that data feed is switched on."}


_scan_cache: Dict[str, Any] = {"at": None, "result": None}
SCAN_TTL_SECONDS = 60


def _today_loss_fraction() -> float:
    """Realized losses from trades closed today, as a fraction of equity (0 when net positive)."""
    today = datetime.now().date().isoformat()
    realized_today = sum(t['pnl'] for t in trading_state.trades if str(t['exit_time']).startswith(today))
    equity = max(trading_state.account_equity, 1.0)
    return max(0.0, -realized_today) / equity


def scan_instrument(instrument: Any, data: Any, real_yield_bps: Optional[float]) -> Dict[str, Any]:
    """Run one instrument through a fresh pipeline. Read-only: no order is ever sent."""
    row: Dict[str, Any] = {
        "symbol": instrument.symbol, "name": instrument.name, "asset_class": instrument.asset_class,
        "underlying": instrument.underlying, "note": instrument.note,
    }
    try:
        hourly, daily = data.hourly_and_daily(instrument.symbol)
        snapshot = snapshot_from_bars(instrument.symbol, hourly, daily)
    except Exception as e:
        return {**row, "error": str(e)}

    macro: Dict[str, Any] = {}
    if instrument.underlying == "gold" and real_yield_bps is not None:
        macro = {"underlying": "gold", "real_yield_change_bps": real_yield_bps}
    term = {"physically_backed": True} if instrument.physically_backed else {}

    position = trading_state.positions.get(instrument.symbol)
    equity = max(trading_state.account_equity, 1.0)
    exposure = position['quantity'] * position['current_price'] / equity if position else 0.0

    # A fresh pipeline per instrument: a scan must not consume the live rate limits.
    result = TradingPipeline().evaluate(
        market_snapshot=snapshot, account_equity=equity, exposure=exposure,
        portfolio_exposure=trading_state.net_position_value() / equity,
        daily_loss_used=_today_loss_fraction(), spread=snapshot.spread, expected_slippage=0.0005,
        liquidity=snapshot.liquidity, asset_class=instrument.asset_class,
        macro_metrics=macro, term_structure=term,
    )
    technical = result["specialists"]["technical"]
    prior_close = daily[-2]["close"] if len(daily) > 1 else daily[-1]["open"]
    return {
        **row,
        "price": snapshot.price,
        "change_1d_pct": (snapshot.price / prior_close - 1.0) * 100 if prior_close else 0.0,
        "atr_pct": snapshot.volatility["atr"] / snapshot.price * 100 if snapshot.price else 0.0,
        "trend_score": technical.get("trend_score", 0.0),
        "trend_votes": technical.get("timeframe_votes", {}),
        "decision": result["decision"],
        "reasons": result["reasons"],
        "order": result["order"],
        "specialists": [
            {"agent": name, "signal": out.get("signal"), "confidence": out.get("confidence", 0.0)}
            for name, out in result["specialists"].items()
        ],
        "as_of": snapshot.timestamp.isoformat(),
    }


@app.get("/api/markets")
async def list_markets():
    return {"instruments": [instrument.__dict__ for instrument in UNIVERSE]}


@app.get("/api/markets/scan")
async def scan_markets(refresh: bool = False):
    """Scan crypto, gold, silver, oil and the S&P 500 benchmark. Cached for a minute."""
    now = datetime.now()
    cached_at = _scan_cache["at"]
    if not refresh and cached_at and (now - cached_at).total_seconds() < SCAN_TTL_SECONDS:
        return _scan_cache["result"]

    if not integrations.status(trading_state.settings)[0]["configured"]:
        raise HTTPException(status_code=409, detail="Connect Alpaca on the Integrations page to scan markets")

    data = AlpacaMarketData(trading_state.settings)
    real_yield_bps: Optional[float] = None
    fred_key = trading_state.settings.fred_api_key.get_secret_value()
    if fred_key:
        try:
            real_yield_bps = await asyncio.to_thread(fred.real_yield_change_bps, fred_key)
        except DataUnavailable as e:
            logger.warning(f"Real-yield data unavailable: {e}")

    rows = await asyncio.gather(*[
        asyncio.to_thread(scan_instrument, instrument, data, real_yield_bps) for instrument in UNIVERSE
    ])
    result = {
        "scanned_at": now.isoformat(),
        "real_yield_change_bps": real_yield_bps,
        "instruments": rows,
    }
    _scan_cache.update(at=now, result=result)
    return result


class KillSwitchRequest(BaseModel):
    reason: str = "manual kill switch"


@app.post("/api/kill-switch")
async def trip_kill_switch(req: KillSwitchRequest):
    """Halt all new entries and flatten every position (at the broker when live)."""
    result = await trading_state.kill_switch(req.reason)
    await manager.broadcast_alert(Alert(
        alert_type="RISK_WARNING",
        message=f"Kill switch tripped: {req.reason}. {result['closed']} position(s) closed.",
        severity="CRITICAL",
        timestamp=datetime.now().isoformat(),
    ))
    return result


@app.post("/api/resume")
async def resume_trading():
    """Re-enable new entries after a kill switch. Does not reopen anything."""
    trading_state.pipeline.guard.resume()
    return {"halted": False}


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "pipeline": "ready",
        "mode": "demo" if trading_state.demo_mode else "live",
        "halted": trading_state.halted,
        "halt_reason": trading_state.pipeline.guard.halt_reason,
    }


# ============================================================================
# Helper Functions
# ============================================================================

async def adjust_position_size(symbol: str, new_qty: Any) -> Dict[str, Any]:
    """Resize a demo position. Increases must stay within the risk engine's asset exposure cap."""
    if not isinstance(new_qty, (int, float)) or new_qty <= 0:
        raise HTTPException(status_code=400, detail="Valid quantity required")
    if not trading_state.demo_mode:
        raise HTTPException(
            status_code=501,
            detail="Size changes are not sent to the broker; close the position and re-enter instead",
        )

    async with trading_state.lock:
        pos = trading_state.positions.get(symbol)
        if pos is None:
            raise HTTPException(status_code=404, detail=f"No position for {symbol}")
        if new_qty > pos['quantity']:
            cap = trading_state.pipeline.risk.max_asset_exposure
            exposure = new_qty * pos['current_price'] / trading_state.account_equity
            if exposure > cap:
                raise HTTPException(
                    status_code=400,
                    detail=f"Rejected: {exposure:.1%} of equity exceeds the {cap:.0%} per-asset exposure cap",
                )
        pos['quantity'] = new_qty
        trading_state._mark(symbol, pos['current_price'])
        logger.info(f"Adjusted {symbol} to {new_qty} shares")
        return {"status": "success", "message": f"Adjusted {symbol} to {new_qty} shares"}


async def update_stop(symbol: str, stop_price: Any) -> Dict[str, Any]:
    """Move a stop. Removing it, or placing it through the current price, is refused."""
    if not isinstance(stop_price, (int, float)) or stop_price <= 0:
        raise HTTPException(status_code=400, detail="A positive stop_price is required; stops cannot be removed")

    async with trading_state.lock:
        pos = trading_state.positions.get(symbol)
        if pos is None:
            raise HTTPException(status_code=404, detail=f"No position for {symbol}")
        is_long = pos['side'] == 'BUY'
        if (is_long and stop_price >= pos['current_price']) or (not is_long and stop_price <= pos['current_price']):
            side = "below" if is_long else "above"
            raise HTTPException(
                status_code=400,
                detail=f"Stop for a {'long' if is_long else 'short'} must be {side} the current price {pos['current_price']:.2f}",
            )
        pos['stop_price'] = float(stop_price)
        logger.info(f"Updated {symbol} stop to ${stop_price}")
        return {"status": "success", "message": f"Stop updated to ${stop_price}"}


async def get_portfolio_snapshot() -> PortfolioDashboard:
    """
    Generate complete portfolio snapshot from trading state.
    Returns real positions, trades, and P&L metrics.
    """
    async with trading_state.lock:
        # Build positions list
        positions = []
        for symbol, pos in trading_state.positions.items():
            positions.append(Position(
                symbol=symbol,
                quantity=pos['quantity'],
                entry_price=pos['entry_price'],
                current_price=pos['current_price'],
                unrealized_pnl=pos['pnl'],
                unrealized_pnl_pct=pos['pnl_pct'],
                side=pos['side'],
                thesis_valid=pos['thesis_valid'],
                stop_price=pos.get('stop_price'),
                target_price=pos.get('target_price'),
            ))
        
        # Total P&L: realized from closed trades plus open P&L
        total_pnl = trading_state.realized_pnl + trading_state.unrealized_pnl()
        total_pnl_pct = (total_pnl / trading_state.initial_equity * 100) if trading_state.initial_equity > 0 else 0.0
        cash = trading_state.cash()
        
        # Calculate max drawdown
        max_drawdown = trading_state.get_max_drawdown()
        
        # Get recent trades (last 20)
        recent_trades = [
            Trade(
                trade_id=t['trade_id'],
                symbol=t['symbol'],
                entry_price=t['entry_price'],
                exit_price=t['exit_price'],
                quantity=t['quantity'],
                side=t['side'],
                pnl=t['pnl'],
                pnl_pct=t['pnl_pct'],
                entry_time=t['entry_time'],
                exit_time=t['exit_time'],
                thesis_status=t['thesis_status'],
                analysis_tags=t['analysis_tags'],
            )
            for t in trading_state.trades[-20:]
        ]
        
        return PortfolioDashboard(
            account_equity=trading_state.account_equity,
            cash=cash,
            buying_power=max(0.0, cash),  # cash account: no margin
            total_pnl=total_pnl,
            total_pnl_pct=total_pnl_pct,
            max_drawdown=max_drawdown,
            positions=positions,
            recent_trades=recent_trades,
            timestamp=datetime.now().isoformat(),
            realized_pnl=trading_state.realized_pnl,
            unrealized_pnl=trading_state.unrealized_pnl(),
            mode="demo" if trading_state.demo_mode else "live",
            halted=trading_state.halted,
            equity_curve=[EquityPoint(t=t, equity=e) for t, e in trading_state.equity_points],
        )


async def parse_and_validate_command(text: str, symbol: Optional[str]) -> CommandResponse:
    """
    Parse natural language command and validate against risk rules.
    Extracts symbol from text if not provided.
    """
    lower_text = text.lower()
    
    # Try to extract symbol from text (e.g., "sell AAPL", "close TSLA at $150")
    if not symbol:
        # Look for uppercase words that might be symbols
        matches = re.findall(r'\b([A-Z]{1,5})\b', text)
        if matches:
            symbol = matches[0]
    
    # Check if position exists
    has_position = symbol and symbol in trading_state.positions if symbol else False
    
    # Parse commands
    if any(word in lower_text for word in ['sell', 'close', 'exit']):
        if not has_position:
            return CommandResponse(
                understood=True,
                reasoning=f"No open position for {symbol}" if symbol else "No symbol specified",
                requires_confirmation=False
            )
        
        return CommandResponse(
            understood=True,
            action="CLOSE_POSITION",
            params={"symbol": symbol},
            reasoning=f"Close {symbol} position at current market price",
            requires_confirmation=True
        )
    
    elif any(word in lower_text for word in ['adjust', 'size', 'reduce', 'increase']):
        if not has_position:
            return CommandResponse(
                understood=True,
                reasoning=f"No open position for {symbol}" if symbol else "No symbol specified",
                requires_confirmation=False
            )
        
        # Try to extract quantity
        qty_match = re.search(r'(\d+)', text)
        quantity = float(qty_match.group(1)) if qty_match else None
        
        return CommandResponse(
            understood=True,
            action="ADJUST_SIZE",
            params={"symbol": symbol, "quantity": quantity},
            reasoning=f"Adjust {symbol} position size",
            requires_confirmation=True
        )
    
    elif "portfolio" in lower_text or "summary" in lower_text:
        return CommandResponse(
            understood=True,
            action="SHOW_SUMMARY",
            reasoning="Show portfolio summary",
            requires_confirmation=False
        )
    
    elif "news" in lower_text or "alert" in lower_text:
        return CommandResponse(
            understood=True,
            action="SHOW_ALERTS",
            reasoning="Show recent alerts and news",
            requires_confirmation=False
        )
    
    else:
        return CommandResponse(
            understood=False,
            reasoning="Could not understand command. Try: 'close AAPL', 'adjust size', 'show summary'",
            requires_confirmation=False
        )


async def handle_command(websocket: WebSocket, data: Dict[str, Any]):
    """Handle natural language command from client"""
    text = data.get("text", "")
    symbol = data.get("symbol")
    
    response = await parse_and_validate_command(text, symbol)
    
    await websocket.send_json({
        "type": "command_response",
        "data": response.model_dump()
    })


async def handle_action(websocket: WebSocket, data: Dict[str, Any]):
    """Handle manual action from client"""
    try:
        result = await execute_action(data)
        await websocket.send_json({
            "type": "action_result",
            "data": result
        })
    except HTTPException as e:
        await websocket.send_json({
            "type": "action_error",
            "error": str(e.detail)
        })


# ============================================================================
# Background Tasks
# ============================================================================

def find_exits(positions: Dict[str, Dict[str, Any]]) -> List[tuple]:
    """(symbol, price, reason) for every position whose stop, target, or thesis has triggered."""
    exits = []
    for symbol, pos in positions.items():
        is_long = pos['side'] == 'BUY'
        price = pos['current_price']

        # Stop sits below entry for longs, above for shorts
        stop = pos.get('stop_price')
        if stop and ((is_long and price <= stop) or (not is_long and price >= stop)):
            exits.append((symbol, price, "hit_stop"))
            continue

        target = pos.get('target_price')
        if target and ((is_long and price >= target) or (not is_long and price <= target)):
            exits.append((symbol, price, "hit_target"))
            continue

        if not pos['thesis_valid']:
            exits.append((symbol, price, "thesis_invalidated"))
    return exits


async def monitor_positions():
    """Background task to monitor positions and check for exit conditions"""
    while True:
        try:
            await asyncio.sleep(1)  # Check every second

            # Decide and close under one hold of the lock. Calling the public
            # close_position() here would re-acquire it and deadlock the app.
            async with trading_state.lock:
                results = [
                    (symbol, exit_price, reason, trading_state._close_position_locked(symbol, exit_price, reason))
                    for symbol, exit_price, reason in find_exits(trading_state.positions)
                ]

            for symbol, exit_price, reason, result in results:
                if result["success"]:
                    message, severity = f"Position closed: {reason} at ${exit_price:.2f}", "WARNING" if reason == "hit_stop" else "INFO"
                else:
                    message, severity = f"Exit {reason} FAILED: {result.get('error')}", "CRITICAL"
                await manager.broadcast_alert(Alert(
                    alert_type="POSITION_ALERT" if result["success"] else "EXECUTION_FAILURE",
                    symbol=symbol,
                    message=message,
                    severity=severity,
                    timestamp=datetime.now().isoformat()
                ))

        except Exception as e:
            logger.error(f"Error in position monitoring: {e}")
            await asyncio.sleep(1)


async def broadcast_portfolio_updates():
    """Background task to broadcast portfolio updates to all clients"""
    while True:
        try:
            await asyncio.sleep(0.5)  # Update every 500ms
            
            if manager.active_connections:
                portfolio = await get_portfolio_snapshot()
                await manager.broadcast({
                    "type": "portfolio_update",
                    "data": portfolio.model_dump()
                })
        
        except Exception as e:
            logger.error(f"Error broadcasting portfolio: {e}")
            await asyncio.sleep(0.5)


async def simulate_market_data():
    """Background task to simulate price updates for demo positions only.

    Once real broker positions are loaded this does nothing: simulated prices
    must never touch a live book.
    """
    while True:
        try:
            await asyncio.sleep(2)  # Update prices every 2 seconds
            if not trading_state.demo_mode:
                continue

            async with trading_state.lock:
                for symbol, pos in list(trading_state.positions.items()):
                    # Simulate random price movement (±0.5%)
                    change = random.uniform(-0.005, 0.005)
                    trading_state._mark(symbol, pos['current_price'] * (1 + change))

        except Exception as e:
            logger.error(f"Error in market data simulation: {e}")
            await asyncio.sleep(2)


@app.on_event("startup")
async def startup_event():
    """Initialize on app startup"""
    logger.info("Dashboard API starting up...")
    
    # Create background tasks
    asyncio.create_task(monitor_positions())
    asyncio.create_task(broadcast_portfolio_updates())
    asyncio.create_task(simulate_market_data())
    
    logger.info("Background tasks started")
    
    # Try to load real Alpaca positions first
    alpaca_loaded = await trading_state.load_alpaca_positions()
    
    # If no Alpaca positions, add demo positions
    if not alpaca_loaded:
        logger.info("Using demo positions")
        await trading_state.add_position("AAPL", 100, 150.00, "BUY", "Strong technical breakout")
        await trading_state.add_position("TSLA", 50, 200.00, "BUY", "Positive earnings surprise")
        
        # Set stops and targets
        async with trading_state.lock:
            trading_state.positions["AAPL"]['stop_price'] = 145.00
            trading_state.positions["AAPL"]['target_price'] = 160.00
            trading_state.positions["TSLA"]['stop_price'] = 190.00
            trading_state.positions["TSLA"]['target_price'] = 220.00


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on app shutdown"""
    logger.info("Dashboard API shutting down...")
    # TODO: Close data streams
    # TODO: Save state


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        # Localhost only: these endpoints can close live positions and have no auth.
        host="127.0.0.1",
        port=8000,
        reload=False,  # Disable hot reload to avoid multiprocessing issues
        log_level="info"
    )

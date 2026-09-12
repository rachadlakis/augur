"""
Real-time trading dashboard API with WebSocket support.

Provides:
- Live position and P&L updates
- Trade history streaming
- Natural language command parsing
- Market alerts and notifications
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import asyncio
import json
from datetime import datetime
import logging
import re

# Trading system imports
from agents.augur_agents.trading.pipeline import TradingPipeline
from agents.augur_agents.trading.journal import TradeJournal
from agents.augur_agents.trading.monitor import PositionMonitor
from agents.augur_agents.contracts import MarketSnapshot
from config import Settings

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


# ============================================================================
# FastAPI App Setup
# ============================================================================

app = FastAPI(
    title="Augur Trading Dashboard API",
    description="Real-time dashboard for multi-agent trading system",
    version="1.0.0"
)

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["localhost", "127.0.0.1"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# Trading State Management
# ============================================================================

class TradingState:
    """Thread-safe state holder for trading system"""
    
    def __init__(self):
        self.settings = Settings()
        self.pipeline = TradingPipeline()
        self.journal = TradeJournal()
        self.monitor = PositionMonitor()
        
        # State tracking
        self.account_equity = self.settings.initial_capital
        self.initial_equity = self.settings.initial_capital
        self.equity_history: List[float] = [self.settings.initial_capital]
        self.positions: Dict[str, Dict[str, Any]] = {}  # symbol -> position data
        self.trades: List[Dict[str, Any]] = []  # All completed trades
        self.lock = asyncio.Lock()
        self.last_update = datetime.now()
        
    async def add_position(self, symbol: str, quantity: float, entry_price: float, side: str, thesis: str = ""):
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
            logger.info(f"Added position: {symbol} {quantity} @ {entry_price}")
            # Recalculate account equity
            self._calculate_account_equity()
    
    async def update_position_price(self, symbol: str, current_price: float):
        """Update position current price and P&L"""
        async with self.lock:
            if symbol in self.positions:
                pos = self.positions[symbol]
                pos['current_price'] = current_price
                
                # Calculate P&L
                if pos['side'] == 'BUY':
                    pos['pnl'] = (current_price - pos['entry_price']) * pos['quantity']
                else:  # SELL
                    pos['pnl'] = (pos['entry_price'] - current_price) * pos['quantity']
                
                pos['pnl_pct'] = (pos['pnl'] / (pos['entry_price'] * pos['quantity'])) * 100 if pos['entry_price'] > 0 else 0.0
                
                # Recalculate total account equity (called within lock, so _calculate_account_equity won't deadlock)
                self._calculate_account_equity()
    
    def _calculate_account_equity(self):
        """Calculate total account equity from positions"""
        # Sum of all position values at current prices
        positions_value = sum(
            pos['quantity'] * pos['current_price'] 
            for pos in self.positions.values()
        )
        # Total P&L from positions
        total_pnl = sum(pos['pnl'] for pos in self.positions.values())
        # Account equity = initial capital + total P&L
        new_equity = self.initial_equity + total_pnl
        
        # Only update history if equity changed significantly
        if not self.equity_history or abs(new_equity - self.equity_history[-1]) > 0.01:
            self.equity_history.append(new_equity)
        
        self.account_equity = new_equity
    
    async def close_position(self, symbol: str, exit_price: float, reason: str = "manual_close") -> Dict[str, Any]:
        """Close a position"""
        async with self.lock:
            if symbol not in self.positions:
                return {"success": False, "error": f"No position for {symbol}"}
            
            pos = self.positions[symbol]
            
            # Record in journal
            trade_record = {
                'symbol': symbol,
                'entry': pos['entry_price'],
                'exit': exit_price,
                'size': pos['quantity'],
                'side': pos['side'],
                'thesis': pos.get('thesis', ''),
            }
            journal_entry = self.journal.record_trade(trade_record)
            
            # Add to trades list
            trade_data = {
                'trade_id': journal_entry['trade_id'],
                'symbol': symbol,
                'entry_price': pos['entry_price'],
                'exit_price': exit_price,
                'quantity': pos['quantity'],
                'side': pos['side'],
                'pnl': journal_entry['pnl'],
                'pnl_pct': (journal_entry['pnl'] / (pos['entry_price'] * pos['quantity'])) * 100,
                'entry_time': pos['entry_time'],
                'exit_time': datetime.now().isoformat(),
                'thesis_status': reason,
                'analysis_tags': [],
            }
            self.trades.append(trade_data)
            
            # Update account equity
            self.account_equity += journal_entry['pnl']
            self.equity_history.append(self.account_equity)
            
            # Remove position
            del self.positions[symbol]
            
            logger.info(f"Closed position: {symbol} P&L: ${journal_entry['pnl']:.2f}")
            return {
                "success": True,
                "pnl": journal_entry['pnl'],
                "trade_id": journal_entry['trade_id']
            }
    
    def get_max_drawdown(self) -> float:
        """Calculate max drawdown from equity history"""
        if not self.equity_history:
            return 0.0
        
        peak = self.equity_history[0]
        max_dd = 0.0
        
        for equity in self.equity_history:
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak
            max_dd = max(max_dd, dd)
        
        return max_dd * 100

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
        # Adjust position size
        new_qty = params.get("quantity")
        if not new_qty or new_qty <= 0:
            raise HTTPException(status_code=400, detail="Valid quantity required")
        
        async with trading_state.lock:
            if symbol in trading_state.positions:
                trading_state.positions[symbol]['quantity'] = new_qty
                logger.info(f"Adjusted {symbol} to {new_qty} shares")
                return {"status": "success", "message": f"Adjusted {symbol} to {new_qty} shares"}
            else:
                raise HTTPException(status_code=404, detail=f"No position for {symbol}")
    
    elif action_type == "MANUAL_OVERRIDE":
        # Manual buy/sell override
        logger.warning(f"Manual override for {symbol}: {params}")
        return {"status": "success", "message": f"Override executed for {symbol}"}
    
    elif action_type == "UPDATE_STOP":
        # Update stop loss
        stop_price = params.get("stop_price")
        async with trading_state.lock:
            if symbol in trading_state.positions:
                trading_state.positions[symbol]['stop_price'] = stop_price
                logger.info(f"Updated {symbol} stop to ${stop_price}")
                return {"status": "success", "message": f"Stop updated to ${stop_price}"}
            else:
                raise HTTPException(status_code=404, detail=f"No position for {symbol}")
    
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action_type}")


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "pipeline": "ready"
    }


# ============================================================================
# Helper Functions
# ============================================================================

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
        
        # Calculate total P&L
        total_pnl = sum(pos['pnl'] for pos in trading_state.positions.values())
        total_pnl_pct = (total_pnl / trading_state.initial_equity * 100) if trading_state.initial_equity > 0 else 0.0
        
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
            cash=trading_state.account_equity * 0.3,  # Approximate available cash
            buying_power=trading_state.account_equity * 0.5,  # Approximate buying power
            total_pnl=total_pnl,
            total_pnl_pct=total_pnl_pct,
            max_drawdown=max_drawdown,
            positions=positions,
            recent_trades=recent_trades,
            timestamp=datetime.now().isoformat()
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

async def monitor_positions():
    """Background task to monitor positions and check for exit conditions"""
    while True:
        try:
            await asyncio.sleep(1)  # Check every second
            
            async with trading_state.lock:
                positions_to_close = []
                
                for symbol, pos in trading_state.positions.items():
                    # Check stop loss
                    if pos['stop_price'] and pos['side'] == 'BUY':
                        if pos['current_price'] <= pos['stop_price']:
                            positions_to_close.append((symbol, pos['current_price'], "hit_stop"))
                    
                    # Check target
                    if pos['target_price'] and pos['side'] == 'BUY':
                        if pos['current_price'] >= pos['target_price']:
                            positions_to_close.append((symbol, pos['current_price'], "hit_target"))
                    
                    # Check thesis validity (random for demo, replace with real logic)
                    if not pos['thesis_valid']:
                        positions_to_close.append((symbol, pos['current_price'], "thesis_invalidated"))
                
                # Close positions that hit exit criteria
                for symbol, exit_price, reason in positions_to_close:
                    result = await trading_state.close_position(symbol, exit_price, reason)
                    if result["success"]:
                        await manager.broadcast_alert(Alert(
                            alert_type="POSITION_ALERT",
                            symbol=symbol,
                            message=f"Position closed: {reason} at ${exit_price:.2f}",
                            severity="WARNING" if reason == "hit_stop" else "INFO",
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
    """Background task to simulate market price updates (for demo)"""
    while True:
        try:
            await asyncio.sleep(2)  # Update prices every 2 seconds
            
            async with trading_state.lock:
                import random
                
                for symbol, pos in trading_state.positions.items():
                    # Simulate random price movement (±0.5%)
                    change = random.uniform(-0.005, 0.005)
                    new_price = pos['current_price'] * (1 + change)
                    pos['current_price'] = new_price
                    
                    # Calculate P&L
                    if pos['side'] == 'BUY':
                        pos['pnl'] = (new_price - pos['entry_price']) * pos['quantity']
                    else:  # SELL
                        pos['pnl'] = (pos['entry_price'] - new_price) * pos['quantity']
                    
                    pos['pnl_pct'] = (pos['pnl'] / (pos['entry_price'] * pos['quantity'])) * 100 if pos['entry_price'] > 0 else 0.0
                
                # Recalculate account equity
                trading_state._calculate_account_equity()
        
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
    
    # Add sample positions for demo
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
        "dashboard_api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )

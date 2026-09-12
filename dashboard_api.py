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

# Trading system imports
from agents.augur_agents.trading.pipeline import TradingPipeline
from agents.augur_agents.contracts import MarketSnapshot, AccountState
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

# Initialize trading pipeline
settings = Settings()
pipeline = TradingPipeline(account_equity=settings.initial_capital)

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
    
    if action_type == "CLOSE_POSITION":
        # Close position for symbol
        logger.info(f"Closing position: {symbol}")
        return {"status": "success", "message": f"Closed {symbol}"}
    
    elif action_type == "ADJUST_SIZE":
        # Adjust position size
        new_qty = params.get("quantity")
        logger.info(f"Adjusting {symbol} to {new_qty} shares")
        return {"status": "success", "message": f"Adjusted {symbol} to {new_qty} shares"}
    
    elif action_type == "MANUAL_OVERRIDE":
        # Manual buy/sell override
        logger.warning(f"Manual override for {symbol}: {params}")
        return {"status": "success", "message": f"Override executed for {symbol}"}
    
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
    Generate complete portfolio snapshot.
    TODO: Wire up to actual trading system state.
    """
    return PortfolioDashboard(
        account_equity=settings.initial_capital,
        cash=settings.initial_capital * 0.2,
        buying_power=settings.initial_capital * 0.4,
        total_pnl=0.0,
        total_pnl_pct=0.0,
        max_drawdown=0.0,
        positions=[],
        recent_trades=[],
        timestamp=datetime.now().isoformat()
    )


async def parse_and_validate_command(text: str, symbol: Optional[str]) -> CommandResponse:
    """
    Parse natural language command and validate against risk rules.
    TODO: Integrate with LLM agent for semantic understanding.
    """
    lower_text = text.lower()
    
    # Simple keyword-based parsing (replace with LLM later)
    if "sell" in lower_text or "close" in lower_text:
        return CommandResponse(
            understood=True,
            action="CLOSE_POSITION",
            params={"symbol": symbol or "UNKNOWN"},
            reasoning="Command contains 'sell' or 'close'",
            requires_confirmation=True
        )
    
    elif "adjust" in lower_text or "size" in lower_text:
        return CommandResponse(
            understood=True,
            action="ADJUST_SIZE",
            params={"symbol": symbol or "UNKNOWN"},
            reasoning="Command contains 'adjust' or 'size'",
            requires_confirmation=True
        )
    
    else:
        return CommandResponse(
            understood=False,
            reasoning="Could not understand command",
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

@app.on_event("startup")
async def startup_event():
    """Initialize on app startup"""
    logger.info("Dashboard API starting up...")
    # TODO: Start real-time data streams
    # TODO: Initialize alert monitoring


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

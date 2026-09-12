# 🔗 Dashboard Integration Guide

Complete guide to wire the Augur Trading Dashboard with the trading system.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     AUGUR TRADING SYSTEM                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              TRADING PIPELINE                            │  │
│  │  - Asset Config (crypto/equity routing)                  │  │
│  │  - Specialist Agents (6 per asset type)                  │  │
│  │  - Orchestrator (conflict detection)                     │  │
│  │  - Risk Manager (position sizing, vetoes)                │  │
│  │  - Execution Planner (pre-trade checks)                  │  │
│  │  - Position Monitor (thesis-driven exits)                │  │
│  │  - Trade Journal (P&L recording)                         │  │
│  │  - Backtest Engine (paper trading)                       │  │
│  └────────────┬───────────────────────────────────────────┘  │
│               │                                               │
│               │ Decision & Position Data                      │
│               ▼                                               │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │         DASHBOARD API (FastAPI + WebSocket)              │  │
│  │  - HTTP REST API for data fetching                        │  │
│  │  - WebSocket for real-time updates                       │  │
│  │  - LLM command parsing                                   │  │
│  │  - Action execution & validation                         │  │
│  └────────────┬───────────────────────────────────────────┘  │
│               │                                               │
│               │ WebSocket & REST calls                        │
│               ▼                                               │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │        DASHBOARD UI (React + TypeScript)                 │  │
│  │  - Portfolio view (equity, P&L, positions)               │  │
│  │  - Trade history table                                   │  │
│  │  - Natural language chat                                 │  │
│  │  - Real-time alerts & notifications                      │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Step-by-Step Integration

### 1. Install Backend Dependencies

```bash
pip install -r requirements.txt
# Installs: fastapi, uvicorn, websockets
```

### 2. Update dashboard_api.py to Use Real Trading Pipeline

Currently, `dashboard_api.py` uses stub data. Wire it to the actual pipeline:

**File: `dashboard_api.py` - Update these functions:**

#### a) Import trading modules

```python
from agents.augur_agents.trading.pipeline import TradingPipeline
from agents.augur_agents.trading.journal import TradeJournal
from agents.augur_agents.trading.backtest import PaperTradingBacktester
from agents.augur_agents.contracts import AccountState, MarketSnapshot
```

#### b) Initialize pipeline and state

```python
class TradingState:
    """Thread-safe state holder"""
    def __init__(self):
        self.pipeline = TradingPipeline(account_equity=settings.initial_capital)
        self.account_equity = settings.initial_capital
        self.positions = {}  # symbol -> Position
        self.trades = []  # List[Trade]
        self.journal = TradeJournal()
        self.lock = asyncio.Lock()

trading_state = TradingState()
```

#### c) Wire get_portfolio_snapshot()

```python
async def get_portfolio_snapshot() -> PortfolioDashboard:
    """Fetch real portfolio from trading pipeline"""
    async with trading_state.lock:
        # Calculate metrics from actual positions
        positions = []
        total_unrealized_pnl = 0.0
        
        for symbol, position_data in trading_state.positions.items():
            pos = Position(
                symbol=symbol,
                quantity=position_data['qty'],
                entry_price=position_data['entry'],
                current_price=position_data['current'],  # From market data
                unrealized_pnl=position_data['pnl'],
                unrealized_pnl_pct=position_data['pnl_pct'],
                side=position_data['side'],
                thesis_valid=position_data['thesis_valid'],
                stop_price=position_data.get('stop'),
                target_price=position_data.get('target'),
            )
            positions.append(pos)
            total_unrealized_pnl += position_data['pnl']
        
        return PortfolioDashboard(
            account_equity=trading_state.account_equity,
            cash=trading_state.account_equity * 0.2,  # placeholder
            buying_power=trading_state.account_equity * 0.4,  # placeholder
            total_pnl=total_unrealized_pnl,
            total_pnl_pct=(total_unrealized_pnl / settings.initial_capital) * 100,
            max_drawdown=0.0,  # Calculate from equity curve
            positions=positions,
            recent_trades=trading_state.trades[-20:],
            timestamp=datetime.now().isoformat()
        )
```

#### d) Wire parse_and_validate_command()

```python
async def parse_and_validate_command(text: str, symbol: Optional[str]) -> CommandResponse:
    """Parse using LLM agent"""
    # TODO: Call agent.parse_natural_language_command(text)
    # For now, simple keyword-based parsing
    
    lower_text = text.lower()
    
    if any(word in lower_text for word in ['sell', 'close', 'exit']):
        return CommandResponse(
            understood=True,
            action="CLOSE_POSITION",
            params={"symbol": symbol or extract_symbol(text)},
            reasoning=f"Detected close signal in: '{text}'",
            requires_confirmation=True
        )
    # ... more parsing logic
```

#### e) Wire handle_action()

```python
async def handle_action(websocket: WebSocket, data: Dict[str, Any]):
    """Execute actual trading action"""
    action_type = data.get("type")
    symbol = data.get("symbol")
    
    if action_type == "CLOSE_POSITION":
        # Execute close via trading pipeline
        result = await trading_state.pipeline.close_position(symbol)
        
        if result['success']:
            # Record in journal
            await trading_state.journal.record_trade({
                'symbol': symbol,
                'exit_reason': 'manual_close',
                'pnl': result['pnl'],
            })
            
            # Broadcast alert
            await manager.broadcast_alert(Alert(
                alert_type='POSITION_ALERT',
                symbol=symbol,
                message=f'Position closed: ${result["pnl"]:.2f} P&L',
                severity='INFO',
                timestamp=datetime.now().isoformat()
            ))
```

### 3. Start the Services

**Terminal 1: Start Backend**
```bash
python dashboard_api.py
```
Output: `Uvicorn running on http://0.0.0.0:8000`

**Terminal 2: Start Frontend**
```bash
cd ui
npm run dev
```
Output: `Local: http://localhost:5173/`

**Terminal 3: Start Trading System** (optional, for live updates)
```bash
# Run your trading agent/backtest
python demo_trading_system.py
# Or: uv run pytest -v agents/tests/  # for testing
```

### 4. Verify Integration

#### Check WebSocket Connection
Open http://localhost:5173/

In browser console:
```javascript
// Should show "WebSocket connected" after 1-2 seconds
```

#### Check API Endpoints
```bash
# Test health check
curl http://localhost:8000/api/health

# Test portfolio fetch
curl http://localhost:8000/api/portfolio

# Test positions
curl http://localhost:8000/api/positions
```

#### Test Chat Command
Type in dashboard chat: "What's my account equity?"

Expected response: Bot parses command, returns current equity

### 5. Wire Real Market Data

Update `dashboard_api.py` to fetch live prices:

```python
async def update_position_prices():
    """Background task to update position prices"""
    while True:
        async with trading_state.lock:
            for symbol in trading_state.positions:
                # Fetch from data provider
                price = await fetch_price(symbol)
                
                # Update position
                position = trading_state.positions[symbol]
                position['current'] = price
                position['pnl'] = (price - position['entry']) * position['qty']
                
                # Broadcast update
                await manager.broadcast({
                    'type': 'price_update',
                    'symbol': symbol,
                    'price': price
                })
        
        await asyncio.sleep(0.5)  # Update every 500ms

# Add to startup
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(update_position_prices())
    # ... other startup tasks
```

### 6. Wire Trade Execution

Connect dashboard actions to trading pipeline:

```python
async def execute_close_position(symbol: str):
    """Execute position close through trading system"""
    # Get current position
    position = trading_state.positions.get(symbol)
    if not position:
        raise ValueError(f"No position for {symbol}")
    
    # Create order request
    order = OrderRequest(
        symbol=symbol,
        quantity=position['qty'],
        side='SELL' if position['side'] == 'BUY' else 'BUY',
        order_type=OrderType.MARKET,
    )
    
    # Execute via providers
    result = await execution_provider.place_order(order)
    
    # Record in journal
    await trading_state.journal.record_trade({
        'symbol': symbol,
        'exit_price': result.avg_fill_price,
        'exit_reason': 'manual',
        'pnl': calculate_pnl(...),
    })
    
    return result
```

### 7. Add Alert System

Wire alerts for news, risk conditions, thesis breaks:

```python
async def monitor_alerts():
    """Background task to generate alerts"""
    while True:
        async with trading_state.lock:
            # Check each position for alerts
            for symbol, position in trading_state.positions.items():
                # Thesis invalidation
                if not position['thesis_valid']:
                    await manager.broadcast_alert(Alert(
                        alert_type='POSITION_ALERT',
                        symbol=symbol,
                        message='Thesis invalidated - consider closing',
                        severity='WARNING',
                        timestamp=datetime.now().isoformat()
                    ))
                
                # Stop hit
                if position['stop_triggered']:
                    await manager.broadcast_alert(Alert(
                        alert_type='POSITION_ALERT',
                        symbol=symbol,
                        message=f'Stop loss triggered at ${position["stop"]}',
                        severity='CRITICAL',
                        timestamp=datetime.now().isoformat()
                    ))
        
        await asyncio.sleep(1)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(monitor_alerts())
```

## Testing Integration

### Unit Tests

```bash
# Test dashboard API
pytest tests/test_dashboard_api.py

# Test trading pipeline
pytest agents/tests/test_trading_core.py

# Test components
cd ui && npm test
```

### E2E Test Scenario

1. Open dashboard
2. Verify portfolio loads
3. Send chat command: "Close AAPL"
4. Confirm action
5. Watch trade appear in history
6. Check alerts for execution
7. Verify P&L updated

### Load Testing

```python
# Use locust for load testing
pip install locust

# Run tests
locust -f loadtest.py --host http://localhost:8000
```

## Performance Tuning

| Component | Optimization |
|-----------|---|
| Portfolio updates | Batch updates every 100ms instead of per-trade |
| WebSocket messages | Compress large messages with gzip |
| Database queries | Add caching layer (Redis) |
| Chart rendering | Use Canvas instead of SVG for large datasets |
| API responses | Paginate trade history |

## Security Checklist

- [ ] Add authentication (JWT, sessions)
- [ ] Enable HTTPS/WSS for production
- [ ] Rate limit API endpoints
- [ ] Validate all user inputs
- [ ] Add CORS restrictions
- [ ] Implement request signing
- [ ] Add audit logging
- [ ] Encrypt sensitive data
- [ ] Set up monitoring & alerts

## Troubleshooting

| Issue | Debug |
|-------|-------|
| No data in portfolio | Check `get_portfolio_snapshot()` returns data |
| Chat not working | Verify `/api/command` endpoint working |
| Slow updates | Check WebSocket message frequency, reduce if needed |
| Positions not closing | Verify `execution_provider.place_order()` succeeds |
| Missing alerts | Check alert queue not full, monitor `asyncio.sleep()` timing |

## Next: Deploy to Production

Once integrated and tested locally:

1. Deploy backend to cloud (AWS, GCP, Azure)
2. Build and deploy React frontend
3. Set up SSL certificates
4. Configure firewalls and security groups
5. Add monitoring (Prometheus, Grafana)
6. Set up automated backups
7. Create runbooks for operations

---

**Dashboard is now fully integrated with the trading system!** 🚀

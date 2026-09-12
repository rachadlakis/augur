# 🎯 Augur Trading Dashboard - Setup & Integration Guide

Your full-featured React trading dashboard is ready! Here's how to get it running.

## 🚀 Quick Start

### Step 1: Replace App.tsx

The generated `src/App.tsx` needs to be replaced with the dashboard version. The key differences:
- Imports all dashboard components
- Handles WebSocket connection to backend
- Manages portfolio state and real-time updates

Key imports:
```typescript
import { PortfolioDashboard } from './components/PortfolioDashboard'
import { TradeHistory } from './components/TradeHistory'
import { ChatInterface } from './components/ChatInterface'
import { AlertCenter } from './components/AlertCenter'
```

### Step 2: Update CSS

Replace `src/App.css` with the new styling in `src/App-new.css`

The new CSS includes:
- Dark theme (perfect for trading)
- Responsive grid layout
- Button styles (.btn, .btn-primary, .btn-danger, etc.)
- Component-specific styling in each component's .css file

### Step 3: Start Dev Server

```bash
cd ui
npm run dev
```

Frontend runs on: **http://localhost:5173/**

### Step 4: Start Backend API

```bash
cd ..  # go to repo root
python dashboard_api.py
```

Backend runs on: **http://localhost:8000/**

## 🏗️ Architecture

### Frontend (React + TypeScript + Vite)

**Components:**

1. **PortfolioDashboard** - Shows:
   - Account equity, P&L, cash, buying power
   - Max drawdown and active position count
   - Table of all open positions with close buttons

2. **TradeHistory** - Shows:
   - All completed trades with entry/exit prices
   - P&L and return % for each trade
   - Exit reason (thesis_invalidated, hit_target, hit_stop)
   - Analysis tags (good_execution, aligned_signals, etc.)

3. **ChatInterface** - Let you:
   - Send natural language commands (e.g., "sell AAPL at $150")
   - Get bot responses with execution confirmation
   - Use quick command buttons for common actions
   - See real-time message history

4. **AlertCenter** - Displays:
   - Market news alerts
   - Position alerts
   - Risk warnings
   - Execution failures
   - Dismissable with timestamps

### Backend (FastAPI + WebSocket)

**Endpoints:**

- `GET /api/portfolio` - Current state
- `GET /api/positions` - Active positions
- `GET /api/trades` - Trade history
- `POST /api/command` - Parse natural language
- `POST /api/action` - Execute manual action
- `WS /ws/dashboard` - Real-time updates

**WebSocket Messages:**

Client → Server:
```json
{ "type": "command", "data": { "text": "sell AAPL" } }
{ "type": "action", "data": { "type": "CLOSE_POSITION", "symbol": "AAPL" } }
```

Server → Client:
```json
{ "type": "portfolio_update", "data": { ...PortfolioState } }
{ "type": "alert", "data": { ...Alert } }
```

## 📊 What You Can Do

### View Live Portfolio

- See account equity, total P&L, and cash in real-time
- Watch individual positions with unrealized P&L
- Check thesis validity (green ✓ or red ✗)
- See position stops and targets

### Close Positions

- Click "Close" button on any position
- Or chat: "close AAPL" or "close all positions"

### Monitor Trades

- View all completed trades with full details
- See P&L on wins and losses
- Review why positions exited
- Check analysis tags for calibration

### Chat with Bot

Natural language commands:
- "Sell AAPL at $150 stop" → Close with stop price
- "What's the latest news?" → News summary
- "Check market conditions" → Market analysis
- Custom LLM parsing (integrates with agent pipeline)

### Get Alerts

- 📰 News alerts on high-impact events
- 📍 Position alerts (thesis break, stop hit)
- ⚠️ Risk warnings (max exposure, max daily loss)
- ❌ Execution failures

## 🔧 Development

### Run tests

```bash
npm test
```

### Build for production

```bash
npm run build
```

Outputs to `dist/` folder

### Check TypeScript errors

```bash
npm run type-check
```

## 🚨 Important Files to Modify

1. **`src/App.tsx`** - Main app component
   - Replace entire file with dashboard version
   - Handles WebSocket connection
   - Manages state

2. **`src/App-new.css`** → **`src/App.css`**
   - Replace global styles
   - Includes dark theme, buttons, layout

3. **Component imports in `src/components/`**
   - Already created: PortfolioDashboard, TradeHistory, ChatInterface, AlertCenter
   - Each has its own .tsx and .css file

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| WebSocket connection failed | Check backend is running (`python dashboard_api.py`) |
| API requests 404 | Verify backend endpoints in `dashboard_api.py` |
| No positions showing | Ensure trading pipeline is sending data to API |
| Chat commands not working | Check LLM agent integration in backend |
| Slow updates | Reduce portfolio fetch interval or use WebSocket only |

## 🎨 Customization

### Change colors

Edit `:root` CSS variables in `App-new.css`:
```css
--bg-primary: #0f172a;
--color-success: #10b981;
--color-danger: #ef4444;
/* etc. */
```

### Modify layout

Change grid in `.app-layout`:
```css
grid-template-columns: 1fr 380px;  /* Change proportions */
```

### Add new components

1. Create `src/components/MyComponent.tsx`
2. Create `src/components/MyComponent.css`
3. Export from `src/components/index.ts`
4. Import in `App.tsx`

## 📱 Mobile Support

Current design is optimized for desktop/tablet. Mobile support via:
- Media queries in CSS (already included for <1200px and <768px)
- Stack layout on smaller screens
- Touch-friendly buttons

## 🔐 Security Notes

Currently **no authentication**. Add before production:

1. JWT tokens
2. Session management
3. CORS restrictions
4. Rate limiting
5. Input validation

## 🎯 Next Steps

1. ✅ Frontend: React components + styling
2. ⏳ Backend: Wire dashboard_api.py to real trading pipeline
3. ⏳ LLM: Integrate command parsing with agent pipeline
4. ⏳ Data: Connect real market data feeds
5. ⏳ Testing: E2E tests for workflow
6. ⏳ Deployment: Docker + Kubernetes

## 📚 Resources

- Vite: https://vitejs.dev/
- React: https://react.dev/
- TypeScript: https://www.typescriptlang.org/
- FastAPI: https://fastapi.tiangolo.com/
- WebSocket: https://developer.mozilla.org/en-US/docs/Web/API/WebSocket

---

**Your dashboard is ready! Connect the backend and start trading!** 🚀

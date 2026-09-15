# Augur Trading Strategy — Complete Visual Guide

## System Philosophy

**Determinism + Probabilism:** Specialist LLM agents provide probabilistic judgments; risk management and execution layers are deterministic and veto-proof.

---

## 1. End-to-End Trading Pipeline

```mermaid
graph TD
    A["User / Market Trigger"]:::user
    B["Asset Classifier<br/>Crypto vs Equity"]:::prep
    C["Deploy Specialists<br/>6 Parallel Analyzers"]:::analysis
    D["Orchestrator Consensus<br/>Conflict Detection"]:::decision
    E["Risk Manager<br/>Position Sizing & Veto"]:::risk
    F["Execution Planner<br/>Safety Gates"]:::exec
    G["Order Execution<br/>Market/Limit"]:::trade
    H["Position Monitor<br/>Thesis Tracking"]:::monitor
    I["Exit / Close<br/>Thesis Invalidation"]:::exit

    A --> B
    B --> C
    C --> D
    D --> E
    E --> F
    F --> G
    G --> H
    H --> I

    classDef user fill:#f2f2f2,stroke:#8a8a8a,color:#1c1c1c
    classDef prep fill:#e6f3ff,stroke:#0066cc,color:#1c1c1c
    classDef analysis fill:#fff3e6,stroke:#ff9900,color:#1c1c1c
    classDef decision fill:#e6f9f0,stroke:#00aa66,color:#1c1c1c
    classDef risk fill:#ffe6e6,stroke:#cc0000,color:#1c1c1c
    classDef exec fill:#f0e6ff,stroke:#6600cc,color:#1c1c1c
    classDef trade fill:#e6ffe6,stroke:#00cc00,color:#1c1c1c
    classDef monitor fill:#ffffcc,stroke:#ccaa00,color:#1c1c1c
    classDef exit fill:#ffcccc,stroke:#990000,color:#1c1c1c
```

---

## 2. Specialist Analyzers — Asset-Class Routing

### Crypto Assets (BTC, ETH, SOL)

```mermaid
graph LR
    Input["Crypto Asset"]:::asset
    
    TA["Technical Analyst<br/>OHLC, RSI, MACD<br/>Moving Averages"]:::specialist
    OC["OnChain Analyst<br/>Whale Moves, Funding<br/>Open Interest"]:::specialist
    NS["News Analyst<br/>Headlines, Sentiment<br/>Impact Score"]:::specialist
    DA["Derivatives Analyst<br/>Put/Call Ratios<br/>Basis, Crowding"]:::specialist
    MA["Macro Analyst<br/>DXY, Fed Policy<br/>Economic Flows"]:::specialist
    
    Output["Specialist Outputs<br/>{signal, confidence, evidence}"]:::output
    
    Input --> TA
    Input --> OC
    Input --> NS
    Input --> DA
    Input --> MA
    
    TA --> Output
    OC --> Output
    NS --> Output
    DA --> Output
    MA --> Output
    
    classDef asset fill:#fff3e6,stroke:#ff9900,color:#1c1c1c
    classDef specialist fill:#e6f3ff,stroke:#0066cc,color:#1c1c1c
    classDef output fill:#e6f9f0,stroke:#00aa66,color:#1c1c1c
```

### Equity Assets (AAPL, MSFT, GOOGL)

```mermaid
graph LR
    Input["Equity Asset"]:::asset
    
    TA["Technical Analyst<br/>OHLC, RSI, MACD<br/>Moving Averages"]:::specialist
    FN["Fundamentals Analyst<br/>Earnings, PE, Revenue<br/>Insider Activity"]:::specialist
    NS["News Analyst<br/>Headlines, Sentiment<br/>Impact Score"]:::specialist
    DA["Derivatives Analyst<br/>Put/Call Ratios<br/>Options Flow"]:::specialist
    MA["Macro Analyst<br/>Rates, DXY, Fed<br/>Economic Horizon"]:::specialist
    
    Output["Specialist Outputs<br/>{signal, confidence, evidence}"]:::output
    
    Input --> TA
    Input --> FN
    Input --> NS
    Input --> DA
    Input --> MA
    
    TA --> Output
    FN --> Output
    NS --> Output
    DA --> Output
    MA --> Output
    
    classDef asset fill:#fff3e6,stroke:#ff9900,color:#1c1c1c
    classDef specialist fill:#e6f3ff,stroke:#0066cc,color:#1c1c1c
    classDef output fill:#e6f9f0,stroke:#00aa66,color:#1c1c1c
```

---

## 3. Specialist Signal Structure

Each specialist returns structured data:

```
{
  "signal": "BUY" | "SELL" | "NEUTRAL",
  "confidence": 0.0 to 1.0,
  "evidence_quality": "HIGH" | "MEDIUM" | "LOW",
  "data_freshness": timestamp,
  "risk_flags": ["flag1", "flag2"],
  "reasoning": "..."
}
```

### Signal Strength Calculation
$$\text{signal\_weight} = \text{confidence} \times \text{evidence\_quality\_multiplier} \times \text{freshness\_bonus}$$

---

## 4. Orchestrator Consensus — Weighted Synthesis

```mermaid
graph TD
    S1["Technical Analyst<br/>confidence: 0.8<br/>signal: BUY"]:::specialist
    S2["OnChain Analyst<br/>confidence: 0.6<br/>signal: BUY"]:::specialist
    S3["News Analyst<br/>confidence: 0.4<br/>signal: SELL"]:::specialist
    S4["Derivatives Analyst<br/>confidence: 0.7<br/>signal: BUY"]:::specialist
    S5["Macro Analyst<br/>confidence: 0.5<br/>signal: NEUTRAL"]:::specialist
    
    WEIGHT["Weighted Synthesis<br/>confidence × evidence × freshness"]:::logic
    
    CHECK{"Conflict<br/>Detection"}:::decision
    
    ALIGN["✓ Aligned Signals<br/>BUY weight >> SELL weight"]:::aligned
    CONFLICT["⚠ Conflicted Signals<br/>BUY weight ≈ SELL weight<br/>Apply conflict penalty"]:::conflicts
    
    BUY["Decision: BUY<br/>score: 1.78"]:::outcome
    NOTRADE["Decision: NO_TRADE<br/>score: -0.34<br/>Caution wins"]:::outcome
    
    S1 --> WEIGHT
    S2 --> WEIGHT
    S3 --> WEIGHT
    S4 --> WEIGHT
    S5 --> WEIGHT
    
    WEIGHT --> CHECK
    CHECK -->|Aligned| ALIGN
    CHECK -->|Conflicted| CONFLICT
    
    ALIGN --> BUY
    CONFLICT --> NOTRADE
    
    classDef specialist fill:#e6f3ff,stroke:#0066cc,color:#1c1c1c
    classDef logic fill:#fff3e6,stroke:#ff9900,color:#1c1c1c
    classDef decision fill:#e6f9f0,stroke:#00aa66,color:#1c1c1c
    classDef aligned fill:#e6ffe6,stroke:#00cc00,color:#1c1c1c
    classDef conflicts fill:#ffe6e6,stroke:#cc0000,color:#1c1c1c
    classDef outcome fill:#f0e6ff,stroke:#6600cc,color:#1c1c1c
```

**Key Principle:** No majority voting. Incompatible high-confidence signals trigger `NO_TRADE` (conflict penalty: -0.25).

---

## 5. Position Sizing Formula — Deterministic Risk Layer

```
Given:
  • Account Equity = $100,000
  • Max Risk Per Trade = 2% of equity = $2,000
  • Stop Distance = 2% from entry
  
Calculation:
  Position Notional = (Equity × Risk_Fraction) / Stop_Distance_Fraction
                    = ($100,000 × 0.02) / 0.02
                    = $100,000
```

### Position Size Matrix (Example)

```mermaid
graph TD
    Scenario1["Scenario: Wide Stop (3%)<br/>Max Risk: $2k<br/>Equity: $100k"]:::input
    Calc1["Position = (100k × 0.02) / 0.03<br/>= $66,667"]:::calc
    
    Scenario2["Scenario: Tight Stop (1%)<br/>Max Risk: $2k<br/>Equity: $100k"]:::input
    Calc2["Position = (100k × 0.02) / 0.01<br/>= $200,000"]:::calc
    
    Scenario3["Scenario: Very Tight Stop (0.5%)<br/>Max Risk: $2k<br/>Equity: $100k"]:::input
    Calc3["Position = (100k × 0.02) / 0.005<br/>= $400,000 ⚠ EXCEEDS MAX<br/>Capped at max_exposure"]:::calc
    
    Scenario1 --> Calc1
    Scenario2 --> Calc2
    Scenario3 --> Calc3
    
    classDef input fill:#fff3e6,stroke:#ff9900,color:#1c1c1c
    classDef calc fill:#e6f9f0,stroke:#00aa66,color:#1c1c1c
```

### Risk Manager Veto Conditions

```mermaid
graph TD
    Position["Proposed Position<br/>Size & Entry Price"]:::input
    
    Check1{"Position Notional<br/>< max_exposure?"}:::check
    Check2{"Daily P&L Loss<br/>< max_daily_loss?"}:::check
    Check3{"Liquidity<br/>> min_required?"}:::check
    Check4{"Bid-Ask Spread<br/>< acceptable?"}:::check
    Check5{"Reward/Risk Ratio<br/>> 2.0?"}:::check
    
    Reject["REJECT Trade<br/>❌"]:::reject
    Approve["APPROVE Trade<br/>✓"]:::approve
    
    Position --> Check1
    Check1 -->|No| Reject
    Check1 -->|Yes| Check2
    Check2 -->|No| Reject
    Check2 -->|Yes| Check3
    Check3 -->|No| Reject
    Check3 -->|Yes| Check4
    Check4 -->|No| Reject
    Check4 -->|Yes| Check5
    Check5 -->|No| Reject
    Check5 -->|Yes| Approve
    
    classDef input fill:#fff3e6,stroke:#ff9900,color:#1c1c1c
    classDef check fill:#e6f3ff,stroke:#0066cc,color:#1c1c1c
    classDef reject fill:#ffe6e6,stroke:#cc0000,color:#1c1c1c
    classDef approve fill:#e6ffe6,stroke:#00cc00,color:#1c1c1c
```

---

## 6. Execution Planner — Pre-Trade Safety Gates

```mermaid
graph TD
    OrderRequest["Order Request<br/>Signal Approved<br/>Risk Approved"]:::input
    
    Check1["✓ Market Open?<br/>(Equities) / Exchange Healthy (Crypto)"]:::safety
    Check2["✓ Spread < Threshold?"]:::safety
    Check3["✓ Slippage < Threshold?"]:::safety
    Check4["✓ Liquidity > Required?"]:::safety
    Check5["✓ Signal Freshness < Max Age?"]:::safety
    
    Success["Execute Order<br/>Market or Limit"]:::execute
    Abort["Abort Execution<br/>Defer to Next Window"]:::abort
    
    OrderRequest --> Check1
    Check1 -->|Pass| Check2
    Check1 -->|Fail| Abort
    Check2 -->|Pass| Check3
    Check2 -->|Fail| Abort
    Check3 -->|Pass| Check4
    Check3 -->|Fail| Abort
    Check4 -->|Pass| Check5
    Check4 -->|Fail| Abort
    Check5 -->|Pass| Success
    Check5 -->|Fail| Abort
    
    classDef input fill:#fff3e6,stroke:#ff9900,color:#1c1c1c
    classDef safety fill:#e6f3ff,stroke:#0066cc,color:#1c1c1c
    classDef execute fill:#e6ffe6,stroke:#00cc00,color:#1c1c1c
    classDef abort fill:#ffe6e6,stroke:#cc0000,color:#1c1c1c
```

---

## 7. Position Monitor — Thesis-Driven Exits

```mermaid
graph TD
    OpenPosition["Position Open<br/>Entry: $50,000<br/>Stop: $49,000<br/>Target: $52,000<br/>Thesis: Tech earnings strong"]:::position
    
    Monitor["Continuous Monitoring<br/>Every market update"]:::monitor
    
    Check1["Thesis Intact?<br/>Earnings expectations met?"]:::check
    Check2["Fundamentals Unchanged?<br/>No insider selling"]:::check
    Check3["Risk/Reward Ratio<br/>Still Favorable?"]:::check
    
    Continue["Hold Position<br/>Thesis Active"]:::active
    Exit["Close Position<br/>Thesis Invalidated"]:::exit
    StopLoss["Hit Stop Loss<br/>$49,000"]:::stop
    TakeProfit["Hit Target<br/>$52,000"]:::profit
    
    OpenPosition --> Monitor
    Monitor --> Check1
    Check1 -->|Yes| Check2
    Check1 -->|No| Exit
    Check2 -->|Yes| Check3
    Check2 -->|No| Exit
    Check3 -->|Yes| Continue
    Check3 -->|No| Exit
    Continue --> Monitor
    Monitor -.->|Price Touch| StopLoss
    Monitor -.->|Price Touch| TakeProfit
    
    classDef position fill:#fff3e6,stroke:#ff9900,color:#1c1c1c
    classDef monitor fill:#e6f3ff,stroke:#0066cc,color:#1c1c1c
    classDef check fill:#e6f9f0,stroke:#00aa66,color:#1c1c1c
    classDef active fill:#e6ffe6,stroke:#00cc00,color:#1c1c1c
    classDef exit fill:#ffcccc,stroke:#990000,color:#1c1c1c
    classDef stop fill:#ffe6e6,stroke:#cc0000,color:#1c1c1c
    classDef profit fill:#e6ffe6,stroke:#00cc00,color:#1c1c1c
```

---

## 8. Example Trade Walkthrough

### Scenario: BTC Entry

```mermaid
sequenceDiagram
    participant U as User / System
    participant AC as Asset Classifier
    participant S as Specialists<br/>(5 agents)
    participant O as Orchestrator
    participant R as Risk Manager
    participant E as Executor
    participant M as Position Monitor

    U->>AC: BTC/USD triggered<br/>Price: $42,500
    AC->>S: Deploy crypto specialists
    S->>S: Technical: RSI 65 (overbought)<br/>confidence 0.6
    S->>S: OnChain: Whale accumulating<br/>confidence 0.8
    S->>S: News: Positive sentiment<br/>confidence 0.5
    S->>S: Derivatives: Low crowding<br/>confidence 0.7
    S->>S: Macro: Fed dovish<br/>confidence 0.6
    S->>O: Return all signals
    O->>O: Synthesis: BUY weight = 2.6<br/>SELL weight = 0.4<br/>Conflict penalty: 0 (aligned)
    O->>O: Decision: BUY<br/>confidence score: 1.78
    O->>R: Proposal: BUY BTC<br/>$50k position
    R->>R: Stop: $41,625 (2%)<br/>Risk: $875 (1.75%)
    R->>R: Account equity: $50k<br/>Max risk: 1%<br/>Position = $50k ✓
    R->>R: Liquidity: High ✓<br/>Spread: 0.01% ✓<br/>R/R: 3:1 ✓
    R->>E: APPROVED
    E->>E: Market open? ✓<br/>Spread? ✓<br/>Freshness? ✓
    E->>M: Order executed<br/>Entry: $42,500<br/>Position: $50k<br/>Thesis: Macro + onchain aligned
    M->>M: Monitoring thesis<br/>Stop: $41,625<br/>Target: $43,375
    M->>M: [Continuous updates]
```

---

## 9. System Performance Characteristics

### Test Results (Paper Trading)

```mermaid
graph LR
    Metric1["Win Rate<br/>70%"]:::metric
    Metric2["Profit Factor<br/>1.51"]:::metric
    Metric3["Return<br/>0.35%"]:::metric
    Metric4["Sharpe Ratio<br/>0.55"]:::metric
    Metric5["Max Drawdown<br/>-2.1%"]:::metric
    
    classDef metric fill:#e6f9f0,stroke:#00aa66,color:#1c1c1c,font-weight:bold
```

### Decision Distribution (Demo Run)

- **Aligned signals (BUY):** 40%
- **Aligned signals (SELL):** 20%
- **Conflicted signals (NO_TRADE):** 35%
- **Insufficient data:** 5%

---

## 10. Key Design Constraints

```mermaid
graph TD
    Philosophy["Determinism + Probabilism"]:::core
    
    P1["Risk Layer is<br/>Deterministic & Veto-Proof"]:::principle
    P2["No Majority Voting<br/>Weighted by confidence<br/>× evidence × freshness"]:::principle
    P3["Conflict = Caution<br/>Incompatible signals →<br/>NO_TRADE"]:::principle
    P4["Thesis-Driven Exits<br/>Not reactive P&L"]:::principle
    P5["No Hallucination<br/>DATA_UNAVAILABLE<br/>not fabrication"]:::principle
    P6["Position Sizing<br/>Formula-Based<br/>equity × risk / stop"]:::principle
    
    Philosophy --> P1
    Philosophy --> P2
    Philosophy --> P3
    Philosophy --> P4
    Philosophy --> P5
    Philosophy --> P6
    
    classDef core fill:#f0e6ff,stroke:#6600cc,color:#1c1c1c,font-weight:bold
    classDef principle fill:#e6f3ff,stroke:#0066cc,color:#1c1c1c
```

---

## Quick Reference: Signal Legend

| Symbol | Meaning |
|--------|---------|
| ✓ | Passed safety check |
| ❌ | Failed safety check |
| ⚠️ | Warning / risk flag |
| → | Proceeds to |
| ↔ | Bidirectional communication |
| ✗ | Vetoed / rejected |

---

## Next Steps to Production

1. **Connect real data providers** (Binance, Alpaca, Nansen, Glassnode)
2. **Implement order management** (limit/market, partial fills, time-in-force)
3. **Live P&L dashboard** with thesis tracking
4. **Alert system** (Slack/email on risk violations)
5. **Confidence calibration** from live trade history
6. **Slippage modeling** by asset class and order size

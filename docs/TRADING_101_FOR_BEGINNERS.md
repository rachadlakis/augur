# Trading 101 for Non-Traders

**Goal:** Understand basic trading concepts in 30 minutes. No experience needed.

---

## Part 1: What is Trading?

### Simple Definition
Trading = Buying something cheap, selling it for more money.

**Real example:**
- You buy Bitcoin at $40,000
- Bitcoin price goes to $41,000
- You sell at $41,000
- Profit: $1,000 (on a $40,000 investment = 2.5% return)

**But what if you're wrong?**
- You buy Bitcoin at $40,000
- Bitcoin price DROPS to $39,000
- You sell at $39,000
- Loss: $1,000

---

## Part 2: Key Terms (The Vocabulary You NEED)

### A. Position / Position Size
**What it means:** How much money you're putting into one trade

```
Example:
  Account: $500,000
  Position size: $25,000
  Meaning: "I'm using $25,000 of my account for this one trade"
```

### B. Entry & Exit
**Entry:** The price where you BUY or SELL to start a trade
**Exit:** The price where you CLOSE the trade (take profit or loss)

```
Example:
  Entry: $40,000 (I buy Bitcoin here)
  Exit: $41,000 (I sell Bitcoin here)
  Profit: $1,000
```

### C. Stop Loss
**What it means:** The price where you AUTOMATICALLY EXIT to prevent huge losses

```
Example:
  Buy Bitcoin at: $40,000
  Stop loss set at: $39,200 (2% below entry)
  
  If price drops to $39,200 → system automatically sells
  Maximum loss: $800 per position
  
  Why? To prevent "I'll hold and hope" → turns $800 loss into $40,000 loss
```

### D. Profit Target / Take Profit
**What it means:** The price where you're happy to exit with gains

```
Example:
  Buy Bitcoin at: $40,000
  Profit target: $41,000
  
  If price reaches $41,000 → system closes trade
  Profit: $1,000
```

### E. Win Rate
**What it means:** Percentage of your trades that make money

```
Example:
  Out of 10 trades:
    7 trades make money ✓ (profit)
    3 trades lose money ✗ (loss)
  
  Win rate = 7/10 = 70%
```

### F. Profit Factor
**What it means:** How much you win compared to how much you lose

```
Example:
  Total profit from winning trades: $7,000
  Total loss from losing trades: $4,600
  
  Profit Factor = $7,000 / $4,600 = 1.52
  
  Translation: For every $1 you lose, you make $1.52
  (Above 1.0 is good)
```

### G. Thesis / Trade Thesis
**What it means:** Your reason WHY you think price will go up or down

```
Example theses:
  
  Bitcoin:
    "Fed is printing money → inflation → investors buy Bitcoin"
  
  Apple Stock:
    "New iPhone launches next month → sales will surge → stock up"
  
  Ethereum:
    "Major network upgrade happening → fewer fees → more adoption"
```

### H. Slippage
**What it means:** The price changed between when you wanted to buy and when you actually bought

```
Example:
  You want to: BUY Bitcoin at $40,000
  By the time order executes: Price is $40,050
  Slippage: $50 (or 0.125%)
  
  Why? Markets move fast. By the time your order reaches exchange, price changed.
```

### I. Liquidity
**What it means:** How easy it is to buy/sell without moving the price

```
Example:
  High liquidity: Bitcoin
    Can buy $1M instantly without big price move
  
  Low liquidity: Altcoin "XYZ"
    Buying $1M would crash the price 50%+
    (not good for you)
```

### J. Spread (Bid-Ask Spread)
**What it means:** The difference between the price to BUY vs SELL

```
Example:
  Bid price (what buyers offer): $40,000
  Ask price (what sellers want): $40,010
  Spread: $10 (or 0.025%)
  
  When you buy: You pay $40,010 (ask price)
  When you sell: You get $40,000 (bid price)
  Spread cost: $10 loss on entry
  
  Tight spread = good (easier to trade)
  Wide spread = bad (costs more money)
```

---

## Part 3: How Auger's System Works (30-second version)

### The Problem Augur Solves
```
Normal trading:
  "Bitcoin is up 2% today, I should buy"
  (You make decision based on one signal)
  
  Problem: What if the 2% move was noise? What if macro environment is bad?
           You lose money.

Augur:
  "Let me ask 6 different experts and synthesize their answers smartly"
  
  ✓ Technical expert: "Yes, chart looks good"
  ✓ OnChain expert: "Yes, whales are buying"
  ✓ News expert: "Eh, no major news"
  ✓ Macro expert: "Yes, Fed is dovish"
  ✓ Derivatives expert: "Yes, options show bullish bet"
  ✓ Fundamentals expert: "Yes, earnings growing"
  
  Result: 5 out of 6 agree → HIGH CONFIDENCE BUY
  
  vs. if only 2 agree → CONFLICT → NO TRADE (caution wins)
```

---

## Part 4: The 6 Specialists Explained Simply

### 1. Technical Analyst
**Job:** "Does the chart look good right now?"

**What they look at:**
- Support (price bounces here)
- Resistance (price can't break through)
- Moving averages (is price above/below trend?)
- RSI (is price overbought or oversold?)
- Momentum (is price accelerating up or down?)

**Example answer:**
```
"Bitcoin is above 50-day moving average (bullish)
 RSI is 60 (not overbought)
 Price bounced off support 3 times
 
 SIGNAL: BUY
 CONFIDENCE: 0.8 (pretty confident)"
```

---

### 2. OnChain Analyst (Crypto Only)
**Job:** "What are the rich people (whales) doing?"

**What they look at:**
- Whale wallets (are they buying or selling?)
- Funding rates (is the sentiment bullish or bearish?)
- Open interest (are traders betting up or down?)
- Volume (is there energy behind this move?)

**Example answer:**
```
"Large whale wallets just accumulated 1,000 BTC
 Funding rates positive (traders betting long)
 Volume increasing (shows conviction)
 
 SIGNAL: BUY
 CONFIDENCE: 0.75"
```

---

### 3. News & Sentiment Analyst
**Job:** "Is there good/bad news that matters?"

**What they look at:**
- Major news headlines
- Social media sentiment
- News credibility (official vs. rumors)
- Impact score (does this really matter?)

**Example answer:**
```
"Bitcoin news today:
 - SEC approved Bitcoin ETF ✓ (GOOD)
 - Crypto exchange hack (bad, but small exchange)
 - Some tweet from influencer (noise)
 
 Net sentiment: Positive (real news matters)
 
 SIGNAL: BUY
 CONFIDENCE: 0.65"
```

---

### 4. Derivatives Analyst
**Job:** "What do options traders think?"

**What they look at:**
- Put/Call ratio (more calls = bullish)
- Options volume (are traders betting strong?)
- Open interest concentration (is there crowding?)

**Example answer:**
```
"Options data:
 - Call volume 2x higher than puts (bullish)
 - Large positions NOT concentrated (healthy)
 - IV (volatility) normal
 
 SIGNAL: BUY
 CONFIDENCE: 0.7"
```

---

### 5. Macro Analyst
**Job:** "Is the overall economy helping this asset?"

**What they look at:**
- Federal Reserve policy (printing money or tightening?)
- Dollar strength (strong dollar = Bitcoin might struggle)
- Economic growth (recession vs. boom)
- Interest rates

**Example answer:**
```
"Current macro environment:
 - Fed being 'dovish' (easy money, helpful)
 - Dollar weakening (good for Bitcoin)
 - Economy resilient (people have money to invest)
 
 SIGNAL: BUY
 CONFIDENCE: 0.6"
```

---

### 6. Fundamentals Analyst (Stocks Only)
**Job:** "Is the company doing well financially?"

**What they look at:**
- Earnings growth (revenue increasing?)
- Revenue growth (is business expanding?)
- PE ratio (is stock cheap or expensive?)
- Insider buying (do company leaders believe in it?)

**Example answer:**
```
"Apple fundamentals:
 - Earnings up 15% YoY (great!)
 - Revenue up 12% (solid growth)
 - PE ratio 25 (reasonable vs sector avg 28)
 - Insiders buying stock (good sign)
 
 SIGNAL: BUY
 CONFIDENCE: 0.8"
```

---

## Part 5: How Augur Makes a Decision

### Step 1: Gather All Opinions
```
Technical:     BUY (0.8 confidence)
OnChain:       BUY (0.75 confidence)
News:          BUY (0.65 confidence)
Derivatives:   BUY (0.7 confidence)
Macro:         BUY (0.6 confidence)
Fundamentals:  BUY (0.8 confidence)
```

### Step 2: Weight Them Smartly
**Not by voting** ("5 say BUY, so BUY")
**But by confidence × evidence quality × data freshness**

```
Score = Confidence × Evidence Quality × Freshness

Technical (0.8 × 0.9 × 1.0) = 0.72
OnChain (0.75 × 0.85 × 0.95) = 0.61
News (0.65 × 0.7 × 0.9) = 0.41
Derivatives (0.7 × 0.8 × 1.0) = 0.56
Macro (0.6 × 0.75 × 0.8) = 0.36
Fundamentals (0.8 × 0.9 × 1.0) = 0.72

TOTAL BUY SCORE: 3.38
TOTAL SELL SCORE: 0 (no one said sell)

DECISION: BUY (High Confidence: 3.38)
```

### Step 3: Check for Conflicts
```
If some experts strongly BUY and others strongly SELL:
  → CONFLICT → NO_TRADE
  → (Caution wins over averaging incompatible opinions)

Example:
  Technical: BUY (0.9)
  Macro: SELL (0.9)
  → Conflict detected
  → DECISION: NO_TRADE (wait for clarity)
```

---

## Part 6: Position Sizing (The Math)

### Why This Matters
```
If you risk everything on every trade → one loss destroys your account
If you risk too little → you never make money
```

### Augur's Formula
```
Position Size = (Account × Max Risk %) / Stop Distance %

Example:
  Account: $500,000
  Max risk per trade: 2% = $10,000
  Stop loss distance: 2% from entry
  
  Position = ($500,000 × 0.02) / 0.02
           = $10,000 / 0.02
           = $500,000
  
  BUT: We also cap it to max exposure (e.g., $100,000)
  So: Position size = $100,000
```

### What This Means
```
Your trade:
  Entry: $40,000
  Stop: $39,200 (2% loss)
  Position: $50,000 (on $500k account)
  
Maximum loss if wrong: $1,000 (2% of position)
That's 0.2% of your account (safe)
```

---

## Part 7: Risk Management (Why You Don't Blow Up)

### The Veto Layer
Even if all 6 specialists say BUY, Augur checks:

```
✓ Is position size too large? NO TRADE if yes
✓ Is liquidity enough? NO TRADE if not
✓ Is bid-ask spread too wide? NO TRADE if yes
✓ Is reward/risk ratio 2:1+? NO TRADE if no
✓ Has daily loss limit been hit? NO TRADE if yes
```

**Example:**
```
Specialists say: BUY Bitcoin at $40,000

Risk check 1: Position size = $500,000? 
  TOO BIG → REJECT

This prevents the system from breaking
even if ML models go crazy.
```

---

## Part 8: Position Monitoring (Thesis-Driven Exits)

### Why Augur Exits (Not Just Price Targets)
```
WRONG WAY:
  "I hit my 2% profit target, I'm out!"
  (But thesis is still valid, you left money on table)
  
  or
  
  "I'm down 2%, I'm out!"
  (But thesis is intact, it's just temporary volatility)

RIGHT WAY (Augur):
  "I exit when my THESIS is BROKEN"
  
  Example:
  Original Thesis: "Fed dovish → inflation → Bitcoin up"
  
  Exit triggers:
    - Fed suddenly tightens (thesis broken)
    - Whale wallets start selling (conviction broken)
    - Major negative news (environment changed)
    - Stop loss hit (price action too negative)
```

---

## Part 9: Backtest Results (What Augur Achieved)

```
Testing period: Last 10 trades
Win rate: 70% (7 wins, 3 losses)
Profit factor: 1.51 (wins / losses ratio)
Average return per trade: 0.35%
Max drawdown: -2.1% (worst losing streak)

Translation:
  - 7 out of 10 trades made money ✓
  - For every $1 you lost, you made $1.51 ✓
  - Each trade returned 0.35% on average ✓
  - Worst losing streak: lost 2.1% of account ✓
```

---

## Part 10: What Augur is NOT

```
❌ NOT magic (doesn't predict future perfectly)
❌ NOT risk-free (you can lose money)
❌ NOT a get-rich-quick scheme (0.35% per trade = slow compounding)
❌ NOT better than professional traders
❌ NOT free (costs electricity + API for orchestration)

What it IS:
✓ A systematic way to combine multiple experts
✓ Disciplined risk management
✓ Removes emotional decisions
✓ Thesis-driven (thoughtful exits)
✓ Tested on backtest data
```

---

## Quick Reference: How to Explain Augur to Others

### 30-Second Pitch
```
"Augur is a trading system that asks 6 different AI experts
(technical, on-chain, news, derivatives, macro, fundamentals)
for their opinion on whether to buy or sell.

It combines their answers smartly (not by voting),
enforces strict risk management,
and only trades when there's strong consensus.

Think of it like: instead of one analyst, you have a team."
```

### 2-Minute Explanation
```
"Normal traders look at one thing (e.g., 'RSI is high, so sell')
and make a decision. If they're wrong, they can lose big.

Augur works differently:
1. It gathers analysis from 6 specialists
2. Combines their confidence scores (not voting)
3. If they conflict strongly → NO_TRADE (caution wins)
4. Only trades when 70%+ of specialists agree
5. Enforces strict position sizing + stops
6. Exits when the original thesis is broken (not just for profit)

Example:
  All 6 agree: 'Bitcoin will go up due to Fed dovishness'
  → BUY with 50k position, stop at 2% loss
  
  But 3 say up, 3 say down:
  → NO_TRADE (wait for clarity)

Result: Better win rate, fewer emotional decisions, less risk."
```

### Teaching others about this system
You now have the vocabulary. When someone asks you:

**Q: "How did you decide to buy?"**
A: "I didn't decide. My system asked 6 AI specialists (technical, macro, news, etc.) for their opinion. They all agreed BUY with high confidence. So it did."

**Q: "What if you're wrong?"**
A: "I have a stop loss set at 2% from entry. If I'm wrong, I lose max $X and move on. I risk 0.2% per trade."

**Q: "How does it know when to exit?"**
A: "When the original thesis breaks. If I bought because 'Fed is dovish,' but then Fed suddenly tightens, I exit. It's not about profit targets, it's about thesis integrity."

---

## Summary

You now know:
✓ What trading is (buy low, sell high)
✓ Why risk management matters (stop losses, position sizing)
✓ What each of the 6 specialists does
✓ How Augur combines their opinions
✓ Why consensus + conflict detection > voting
✓ How to explain it to others

You're ready to talk about your system! 🚀

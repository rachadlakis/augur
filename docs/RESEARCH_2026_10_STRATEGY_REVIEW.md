# Strategy research review — October 2026

What current evidence says about the strategies Augur uses or was asked to add,
and what changed in the code as a result. Short version: **there is no
"perfect" strategy.** The edges that hold up are small, survive only with tight
risk control, and the most dependable improvement is refusing bad trades.

## 1. LLM / multi-agent trading in live markets

| Finding | Source | What Augur does with it |
|---|---|---|
| Two-month live benchmark: LLM agents sometimes beat buy-and-hold, but results swing widely by architecture (one framework ranged −38.7% to +21.9% on TSLA depending on the model). Architecture matters more than the model. | *When Agents Trade* (arXiv:2510.11695) | Decisions come from deterministic specialists + a rule-based risk engine, not from a model's free-form call. |
| Six-month production record of two fleets (~7.5M invocations, 14.6K fills): no directional edge (41% vs 50% win rate against a retail benchmark); losses concentrated in volatility-blind sizing; 62% of liquidations came from one aggressive setting; a mechanical bracket recovered ~+39 bps per position. | *What LLM Trading Agents Actually Do in Production* (arXiv:2609.05663) | ATR-scaled stops (size shrinks as volatility rises), bracket orders on every entry, 0.5% risk per trade, entry rate limits. |
| Practitioner reports: backtest-to-live gap is large; a TradingAgents run returned ~7% in 30 days but with 22% drawdowns. | [pinggy.io review](https://pinggy.io/blog/best_ai_trading_agents/) | Daily-loss stop (2%), exposure caps, paper trading by default. |

## 2. Trend following / time-series momentum

| Finding | Source |
|---|---|
| Positive net returns in every decade since 1880, Sharpe ≈ 0.4 after fees. | Hurst, Ooi & Pedersen, via [CXO Advisory](https://www.cxoadvisory.com/momentum-investing/trend-following-with-intrinsic-momentum-over-the-very-long-run) |
| Out-of-sample it is weaker: over 2010–2018 the chance a long/short version beat buy-and-hold on Sharpe was 9–53% depending on the model. | Struck & Cheng, via [CXO Advisory](https://www.cxoadvisory.com/momentum-investing/long-term-tests-of-intrinsic-momentum-across-asset-classes) |
| Trend funds lagged a stock/bond mix by double digits three years running, then had their second-best start on record in early 2026. | [Advisor Perspectives, Jan 2026](https://www.advisorperspectives.com/articles/2026/01/22/trend-chasing-traders-soar-market-whiplash-tests-models) |

**In Augur:** the technical specialist is a multi-timeframe trend vote, but it
can't trade alone (max contribution ≈ 0.18 vs. a 0.25 threshold). It needs a
second, independent primary specialist to agree. Expect long flat stretches.

## 3. Politics and economics news

| Finding | Source |
|---|---|
| Geopolitical risk lowers stock returns across 22 countries (1985–2020); policy uncertainty has a weaker but significant negative effect. | Agoraki, Kouretas & Laopodis, [*Geopolitical risks, uncertainty, and stock market performance*](https://docs.rwu.edu/gsb_fp/207/) |
| Spikes in geopolitical risk bring a significant but **short-lived** drop in U.S. stocks. | Caldara & Iacoviello, [*Measuring Geopolitical Risk*](https://www.lse.ac.uk/economics/Assets/Documents/seminars/mcrw-seminar-papers/measuring-geopolitical-risk.PDF) |
| The only GDELT-based test found no significant effect on U.S. returns (a master's thesis, not peer-reviewed). | [Erasmus thesis](https://thesis.eur.nl/pub/45364/Kroo-W.P.-de-358873-.pdf) |
| Gold moves inversely to real yields. | Erb & Harvey, *The Golden Dilemma* (2013) — already in `MacroAnalyst` |

**In Augur (new):** `providers/news.py` + `PolicyRiskAnalyst`.

* **Economic Policy Uncertainty index** (FRED `USEPUINDXD`): at the 90th
  percentile of its past year or higher, every trade's risk budget is halved.
* **GDELT coverage tone** for rates, inflation, trade, conflict and recession:
  the last 24 h against the prior week. Darker coverage + high uncertainty =
  risk-off lean (down for stocks/crypto/oil, up for gold).
* **Fed press releases**: entries pause for 2 h after an FOMC statement or
  minutes.
* All of it is **secondary evidence** (see §5): the evidence is modest, and news
  is the easiest input for an attacker to fake.

## 4. Whale tracking

| Finding | Source |
|---|---|
| USDT net inflows to exchanges positively predict BTC and ETH returns; ETH net inflows negatively predict ETH returns (1–6 h, 2017–2023). Outflows are not reliably predictive. | [*Return and Volatility Forecasting Using On-Chain Flows*](https://arxiv.org/abs/2411.06327) |
| The biggest "whale" wallets are mostly ETFs and exchanges; a Glassnode analyst reports never having seen real alpha from whale watching. | [Glassnode, *Whale Watching*](https://insights.glassnode.com/the-week-onchain-week-30-2023) |
| No evidence found that copying individual whale wallets works. | — |

**In Augur (new):** `providers/whales.py` + `WhaleFlowAnalyst`. Rather than copy
wallets, Augur reads what the evidence supports: USDT and ETH moving onto and off
seven exchange hot wallets (labels verified on Etherscan, 2026-10-16), straight
from a public Ethereum node. Exchange-to-exchange moves are ignored; a flow
dominated by one transfer is discounted. Secondary evidence only.

## 5. The fake-news fix

`tests/test_fake_news.py` had documented a live vulnerability: spoofed
"newswire" items got full credibility, and news (up to 0.225 of score) could
push a trade over the 0.25 threshold that price action alone (≤ 0.175) never
reached — 12–16 losing trades on a pump-and-dump path. Fixed in
`OrchestratorConsensus`: **secondary evidence (news, policy, whales) can confirm
or veto, but the primary evidence must clear the threshold on its own.** The
three formerly-expected-failure tests now pass.

## 6. Ideas not implemented (and why)

* **Copy-trading named whale wallets** — no supporting evidence; attribution is
  unreliable.
* **LLM reading of headlines** — prompt-injection risk; headline text stays out
  of the decision path.
* **Higher leverage / bigger size on high-conviction calls** — the production
  record above shows this is where losses concentrate. Size only grows through
  the calibrated Kelly path, capped at 0.5% risk per trade.

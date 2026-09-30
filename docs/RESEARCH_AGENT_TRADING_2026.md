# What Makes an LLM Trading Agent Make Money — Research Review (Sept 2026)

Scope: peer-reviewed papers, arXiv preprints, live real-money competitions, and
regulator statements published through 30 Sept 2026, filtered for what is
actionable in Augur. Every number below is quoted from the cited source. Most
sources are **preprints** or industry reports, and that is flagged where it matters.

---

## 0. Bottom line

1. **No one has shown a durable directional edge from an off-the-shelf LLM
   deciding trades.** Live results are mostly negative, and so are the largest
   long-horizon backtests and the only population-scale production record (§1).
2. **Most of the money is lost in the machinery around the model, and so is
   most of the fixable part:** volatility-blind sizing, discretionary exits,
   overtrading, ignored costs, and chasing moves. These problems have firm, cheap
   mechanical fixes (§3, Tier 1).
3. **Switching models is not a lever.** In a paired replay of 416 production
   scenarios, three frontier models were statistically indistinguishable
   (min Holm-adjusted p = 0.46). One cost 25× more than another (§3, Tier 3).
4. **Evidence for real alpha is narrow.** It comes from LLMs used as cross-sectional
   *rankers or researchers* (long top-N stocks) or *factor screeners*, not as
   bar-by-bar traders. Even that is a small number of studies, and it decays as adoption rises (§3, Tier 2).
5. **Most published "LLM beats the market" results are contaminated.** The causes are
   memorized prices, missing costs, or returns that are really market beta.
   Measure selection alpha, not total return (§4).
6. **Augur's architecture is on the right side of the evidence** because it uses
   deterministic risk vetoes and mechanism over prompting. However, the current
   code has 4 P0 defects that match the documented loss modes exactly (§6).

---

## 1. What live and long-horizon evidence actually shows

| Study (date, status) | Setup | Result |
| --- | --- | --- |
| **Alpha Arena S1** (nof1, Oct 18 – Nov 3 2025, real money) | 6 LLMs × $10k, Hyperliquid crypto perps, same prompt | Qwen3 Max **+22.3%**, DeepSeek V3.1 **+4.9%**, Claude Sonnet 4.5 **−30.8%**, Grok 4 **−45.3%**, Gemini 2.5 Pro **−56.7%**, GPT-5 **−62.7%**. Winner made ~43 trades (<3/day). |
| **Alpha Arena S1.5** (US stocks, real money) | 8 models, $320k total | Only Grok 4.20 ended in profit (~+10–12%). Across sessions, the pooled book lost ~⅓; **6 of 32 sessions profitable**. Qwen placed 1,418 trades in one round vs Grok's 158. |
| **DXRG production record** (arXiv 2609.05663, Sep 2026, industry) | 3,505 real-ETH vaults (21 days) + 500–599 Hyperliquid agents (69 days), 7.5M invocations, 14,596 fills | **No directional edge in either fleet.** DXAP roundtrip win rate **41% vs 50%** for a matched retail benchmark. No strategy, template, or cohort had a day-clustered lower bound above zero. |
| **FINSABER** (KDD 2026, peer-reviewed) | 20 years, 100+ symbols | Previously reported LLM advantages "deteriorate significantly". LLM agents are too conservative in bull markets and too aggressive in bear markets. |
| **StockBench** (arXiv 2510.02209) | Multi-month, contamination-free | Most agents fail to beat buy-and-hold. Scores on static financial QA don't predict trading skill. |
| **KTD-Fin** (arXiv 2605.28359) | A-shares, identifiers masked | Top model Qwen3.6-Plus: **+85.29% total return**, but Barra attribution gives **selection alpha −0.7%** (market +41.8%, style +29.2%). **9 of 10 agents had negative selection alpha** (down to −77.8%). |
| **CLQT** (arXiv 2606.29771, Sep 2026) | 1-year contamination-controlled backtest + 4-week live paper | Net of realistic costs, agents "clear defensive baselines but do not cleanly beat the index". The Sharpe "winner" was a reliability artifact from 5 of 26 rounds. |
| **PolyBench** (arXiv 2604.14199) | 38,666 Polymarket markets, Feb 2026 | **2 of 7 models profitable.** Stated confidence stayed at **0.8–0.9 regardless of domain**. Profit "violently contracts" as size approaches $1k because of book depth. |
| **Agent Market Arena** (WWW 2026) | Live multi-market | Some agents beat buy-and-hold on single names, e.g. DeepFundAgent TSLA +8.61% (Sharpe 1.39). Results are highly model- and asset-dependent over short windows. |

**Read:** short live contests are dominated by leverage and luck: both Alpha
Arena winners changed between seasons. The long-horizon and population-scale
studies are consistently null or negative.

---

## 2. Where the money goes: the DXRG production findings

This is the most useful single source, because it measures *why* agents lose,
across 6,400 closed positions. Caveat: most DXAP fills are paper fills with zero
slippage and funding, so real results would be *worse*.

| Defect | Measurement |
| --- | --- |
| **Volatility-blind sizing** | Median leverage is **5.0× in every volatility sextile**, across a 5.7× spread in volatility. Spearman(vol, leverage) = −0.001. Agents size *up* in wilder names (ρ = +0.165). Median realized return falls from **−10.6 bps** (calmest) to **−98.2 bps** (wildest), and the liquidation rate rises from 0.7% to 4.3%. |
| **Uncaptured upside** | **43.2%** of positions reached ≥ +300 bps favorable excursion within 24h, and **49.3% of those closed at a loss**. Median capture where upside existed: **2.0%**. |
| **Discretionary exits** | A fixed **2%/4% stop/target bracket attached at entry** earned **+39.0 bps per position** [CI +21.3, +56.5], and +16.6 bps excluding liquidations. About 60% of the gain comes from truncating the left tail. |
| **Chasing** | Entries after > +0.75% in 1h were over-selected at **2.46×** their availability. Trailing 4h return was +136.5 bps, but forward 4h was −6.9 bps. These picks underperformed random by **−7.82 bps at 1h**. The same pattern replicated in the second system. |
| **Prompt-side risk control fails** | Forcing the model to state its liquidation distance before entry did not change sizing. Agents that stated it liquidated **more** (5.8% vs 1.2%). |
| **Memory contaminates** | Memory-write frequency correlates **negatively** with P&L (ρ = −0.200). One agent traded 31 of 32 positions under a strategy that had been deleted ("ghost strategies"). Agents fabricated funding income on a venue with zero funding. |
| **More information doesn't help** | Adding 770K tokens of context: −0.46 points. A "world context" arm went 0/84. A market-research sub-agent's recommendations were null (n = 120). |
| **Structure beats prose** | Owners who wrote concrete numeric instructions were profitable **4.2×** as often as the median. The UI-only cohort, who never used chat, was the most profitable (41% in profit). |
| **Render effects** | Showing a symbol in the top 3 of a list raised selection **1.75×**, even though its market state was identical to symbols just below the cut. |

The authors call their principle **"mechanism over exhortation"**: every fix that
worked changed the order path or the tool, not the prompt.

---

## 3. What works, ranked by strength of evidence

### Tier 1: Firm, cheap, mostly about *losing less*

1. **Atomic open-with-protection orders.** Stop and target go in the same broker
   order as the entry. This was the highest-value change in the DXRG record. In
   one 48h window, a non-retryable quota error left **24 of 35** fills
   unprotected when the stop was sent separately.
2. **Scale size to realized volatility in code, not in the prompt.** Set the
   stop at k × ATR and size = equity × risk% / stop distance, so dollar risk stays
   constant and notional falls as volatility rises. This agrees with the classic
   result that volatility-managed portfolios raise Sharpe ratios (Moreira & Muir,
   *J. Finance* 2017).
3. **Treat costs and turnover as first-class constraints.** Only **1 of 19**
   closed-loop LLM trading studies modeled transaction costs (Agentic Trading
   survey, arXiv 2605.19337). A 10 bps daily drag cuts a 0.3%/day strategy from
   **112.7% to 65.5%** a year (hedge-fund review, arXiv 2605.05211). In Alpha Arena S1, the low-turnover
   winner (~43 trades) beat the high-turnover losers.
4. **Filter out chasing.** Block or downweight entries after a large 1h move in
   the trade direction. Short-horizon reversal on the venue was negative on 36 of 47 days.
5. **Deterministic risk vetoes that the LLM cannot override.** A slider or
   constraint that overrides strategy text bounded the harm. When strategy text
   won, agents traded far above their configured cadence (DXRG §4.3).
6. **Calibrate confidence against outcomes.** LLM-stated confidence is
   uninformative: fixed at 0.8–0.9 in PolyBench, and CLQT measured a "stating vs. doing" gap
   of +0.30 in backtest and +0.23 live. Map raw confidence to realized hit rate with
   isotonic regression, and score it with Brier/ECE.

### Tier 2: Where real alpha has been reported (moderate evidence, single studies)

7. **LLM as a cross-sectional ranker with autonomous research, long side only.**
   A model ranked the Russell 1000 daily, searching the web itself, strictly live
   since Apr 2025. Long top-20 earned **18.4 bps/day of FF5+momentum alpha, Sharpe
   2.43**, with costs under 10% of gross alpha. Alpha diluted quickly beyond the top
   tier, and **the bottom-ranked stocks had no signal** (arXiv 2601.11958).
   KTD-Fin likewise found that tool-mediated open research beat memory-only modes.
8. **LLM as a factor or alpha screener, not a trader.** Alpha-R1 (GRPO, rewarded
   on realized portfolio returns) reported 12-month out-of-sample S&P 500 returns of **47.9%/yr at
   Sharpe 1.62**. The protocol used a bounded candidate pool, and the study is a preprint.
   The agentic-quant survey (arXiv 2608.31041) finds that systems are concentrated on
   signal discovery, and that forecasting skill "does not reliably translate" into
   live P&L.
9. **News reaction drift, which is decaying.** GPT-4 scores on post-cutoff
   headlines capture the initial reaction, which is not tradable. They also predict
   the subsequent drift, mainly in **small caps and on negative news**. Strategy
   returns **decline as LLM adoption rises** (see the Lopez-Lira line of work).
   Anything built on "LLM reads public news" is the most crowded trade there is.
10. **Prediction markets where the information is text.** On ForecastBench, LLMs were
    statistically indistinguishable from superforecasters as of Jul 2026. In
    PolyBench, political markets gave alpha because polling text is parsable,
    while crypto markets gave deep losses. Capacity is small (~$1k per market).
11. **Fine-tuning on your own decision environment.** Trading-R1 (SFT + RL,
    Tauric) reported better risk-adjusted returns on 6 tickers. It was trained
    on 14 equities over 18 months, so it is small. DXRG's SFT on 41k production turns is
    "early, internal, not validated". This is promising, but you need your own logged data first.

### Tier 3: Weak or negative, so don't spend here

- **Switching models:** decision quality was indistinguishable across frontier
  models, while choice *stability* differed. One model flipped its choice 35% of the
  time on repeats vs 90–95% for the others. Pick a model for cost and stability.
- **Extended thinking:** +26 points on knowledge tasks, **~0 on trading**
  (+0.3 crypto, −0.1 options) (TraderBench, arXiv 2603.00285).
- **More context and more sub-agents:** null (see §2).
- **Free-form long-term memory and reflection:** negative (see §2).
- **Prompt instructions for risk behavior:** negative (see §2).

---

## 4. Evaluation: how to avoid fooling yourself

This is what separates a real edge from a backtest artifact.

| Pitfall | Evidence | Practice |
| --- | --- | --- |
| **Look-ahead via memorization** | LLMs recall historical returns, and masking or instructing them not to use this **fails** (Lopez-Lira, Tang & Zhu 2025). Standard LLMs show alpha decay after their cutoff, while point-in-time models don't (Look-Ahead-Bench). Filtering by membership-inference did not recover alpha (MemGuard-Alpha, a negative result). | Only trust **post-cutoff live or paper** results. For backtests, mask tickers and dates **at the data layer**. De-anonymization then fell to ≤3% (KTD-Fin). |
| **Return ≠ skill** | +85% total return with −0.7% selection alpha (KTD-Fin) | Report market beta, style, and **selection alpha** separately. At minimum, regress on the benchmark. |
| **Wrong inferential unit** | Position-level confidence intervals were **~2.5× too narrow** | Cluster by **day**. Use permutation nulls. |
| **Noise floor** | Byte-identical templates produced a **~$3.5k P&L spread**. A ±15-minute schedule shift flipped results, e.g. −$88 vs +$21 | Run a **null arm**. Ignore any effect smaller than its spread. |
| **Multiple testing** | 1 of 35 variants clearing zero is chance. One rolling p-value went 0.0067 → 0.19 → 0.0277. | Pre-register. Use the **Deflated Sharpe Ratio** (Bailey & López de Prado 2014) and **Probability of Backtest Overfitting** (Bailey et al. 2017). Require t > 3 (Harvey, Liu & Zhu 2016). |
| **Leaky splits** | Random time-series folds leak | Walk-forward or leave-window-out splits. Purged and embargoed CV (López de Prado 2018). |
| **Tool errors hidden** | **14.9%** of tool calls failed at the result level while the transport reported success | Validate every tool payload. |

**How long you must track a strategy.** For daily returns, t ≈ annualized Sharpe × √years.
- Proving Sharpe 1.0 at t = 2 takes **4 years**. At t = 3 it takes **9 years**.
- Sharpe 2.0 at t = 2 takes **1 year**.

A 2-week paper run proves nothing unless the claimed Sharpe is extreme.

---

## 5. Threats specific to agents

- **Prompt injection through data.** Across 15 academic LLM trading schemes,
  **100% had security vulnerabilities** and **80% failed at least one robustness metric** under
  flash-crash-like stress (FARSIGHT SoK, arXiv 2609.19705, Sep 2026). One-sided
  feeds tipped uncertain decisions **from 5% to 100%** (arXiv 2606.00914). Merely
  *reformatting* market data or adding commentary shifts LLM pricing agents. **Input
  canonicalization** removed sentiment attacks (arXiv 2609.18357).
  → Parse news into structured fields (source, timestamp, entity, event type,
  signed score) using a constrained extractor. The decision stage never sees raw
  text, and sources are whitelisted.
- **Non-adaptivity.** 8 of 13 models scored ~33 on crypto with less than 1 point of variation
  across four levels of market manipulation (TraderBench). The agents ran fixed strategies.
- **Herding and regulation.** On 30 Jun 2026, BoE Deputy Governor Breeden warned that
  autonomous agents could "amplify volatility in stress". In June 2026, House Financial Services
  Democrats sent the SEC 13 questions on AI "correlated trading" and "herding". Many agents on
  the same models and feeds means crowded entries and exits.
  → Expect regulators to ask for **kill switches**, audit trails, and rate limits.
  Build them now.

---

## 6. Augur gap analysis (verified against the current code)

> **Status (30 Sept 2026): all items below are fixed.** Regression tests are in
> `agents/tests/test_trading_research_fixes.py` and `tests/test_provider_protection.py`.
> New modules: `trading/calibration.py` (item 6), `trading/evaluation.py`
> (item 10), and `trading/guard.py` (item 11). The line references below point
> to the code *before* the fix.

I checked the following by running the code, not just by reading it.

### P0: matches a documented loss mode exactly

1. **Protective orders are not atomic.** `OrderRequest` has no stop-loss or take-profit
   fields ([providers/base.py:27](../providers/base.py#L27)). Alpaca uses plain
   market, limit, or stop orders, with no `OrderClass.BRACKET`
   ([providers/stocks_alpaca.py:63](../providers/stocks_alpaca.py#L63)).
   Binance has no OCO ([providers/crypto_binance.py:43](../providers/crypto_binance.py#L43)).
   → Add `stop_loss`/`take_profit` to `OrderRequest`. Use an Alpaca bracket order,
   and a Binance OCO on spot or reduce-only stop/take-profit on futures. If protection
   fails, flatten immediately.
2. **Stops are volatility-blind, and confidence goes the wrong way.** The stop is a fixed `price * 0.97`,
   and the target is `1.04–1.08` ([specialists.py:32-33](../agents/augur_agents/trading/specialists.py#L32-L33)).
   Confidence **rises** with ATR ([specialists.py:25](../agents/augur_agents/trading/specialists.py#L25)).
   Measured: 0.575 at ATR 0.5%, 0.65 at 2%, and 0.80 at 5%.
   → Set stop = entry − k·ATR and target = entry + m·ATR. `RiskManager.position_notional`
   then automatically makes size inversely proportional to volatility. Confidence
   should *fall* as volatility rises.
3. **Missing data votes BUY.** When there is no derivatives data, `DerivativesAnalyst` falls into
   `else: BUY` at 0.7 confidence ([specialists.py:118-119](../agents/augur_agents/trading/specialists.py#L118-L119)).
   `MacroAnalyst` does the same with defaults ([specialists.py:147-148](../agents/augur_agents/trading/specialists.py#L147-L148)).
   Measured: with **no** derivatives, macro, or news input, consensus is **BUY** (score
   0.4625). This is a structural long bias, the failure FINSABER and Alpha Arena
   documented ("Claude showed a bullish bias").
   → When input is missing, return `NO_TRADE` with confidence 0 and flag `data_missing`.
4. **The risk engine's sizing is never used.** The pipeline hard-codes `exposure=0.10`
   and `daily_loss_used=0.01`
   ([pipeline.py:61-64](../agents/augur_agents/trading/pipeline.py#L61-L64)).
   Execution uses the caller's `size` rather than `risk_eval["position_notional"]`
   ([pipeline.py:73](../agents/augur_agents/trading/pipeline.py#L73)).
   `max_correlated_exposure` is never checked.
   → Read live exposure and P&L from the provider account, size from the risk
   output, and enforce correlated exposure.

### P1: the backtest will mislead you

5. **Metrics in [backtest.py](../agents/augur_agents/trading/backtest.py) are incorrect.**
   - `sharpe` is return-per-trade × √252, with no volatility term (line 102).
   - `profit_factor` is really the payoff ratio avg_win / avg_loss (line 80). The true
     profit factor is Σwins / |Σlosses|.
   - Slippage is applied only on exit and defaults to 1 bp. There are no fees or funding.
     Binance's standard spot taker fee alone is 10 bps.
   - Drawdown is computed on closed-trade dollar P&L, not on a marked-to-market equity curve.
6. **Confidences are hand-set constants** (0.6, 0.7, 0.55). The weights are not learned.
   The documented schema says `evidence_quality` is `"HIGH"|"MEDIUM"|"LOW"`, but
   `OrchestratorConsensus` calls `float()` on it and raises `ValueError` (verified).
   → Log each specialist's (signal, confidence) with its realized forward return.
   Weight specialists by rolling out-of-sample information coefficient and calibrate
   with isotonic regression. That turns the orchestrator into
   **meta-labeling** (López de Prado 2018): specialists propose a side, and a trained
   secondary model outputs P(profit), which sets the size.
7. **[monitor.py](../agents/augur_agents/trading/monitor.py) only checks stops and targets for `LONG`**
   (lines 25, 33). SHORT positions never hit their stop.
8. **There is no chase filter.** Add a check of the last 1h return in the trade direction.

### P2: infrastructure for any future edge

9. **Decision-provenance ledger.** For each order, the journal should store
   the input snapshot hash, the prompt/template version, the config version, and the
   reconstructed fill. This is what enables replay, model comparison, and later
   fine-tuning (DXRG pillars 3–4). Today [journal.py](../agents/augur_agents/trading/journal.py)
   stores the thesis and outputs only.
10. **Evaluation harness.** It should include:
    - a null arm and day-clustered CIs
    - benchmark-beta attribution
    - Deflated Sharpe
    - a walk-forward split
    - a minimum live paper period sized with the t ≈ SR·√years rule
11. **Kill switch and rate limits**, meaning a global flatten-and-halt. These are
    cheap, and regulators are asking for them.

---

## 7. Suggested roadmap

| Step | What | Why (evidence) |
| --- | --- | --- |
| 1 | Fix P0 1–4 | These match the largest measured losses: +39 bps/position from the bracket, and volatility sizing |
| 2 | Rebuild backtest metrics with fees, both-side slippage, funding, and equity-curve drawdown | Only 1 of 19 studies modeled costs, and cost-free results are the main source of false positives |
| 3 | Log everything and calibrate the specialists | Stated confidence is uninformative. Learned weights plus meta-labeling are the standard fix. |
| 4 | Run 3+ months of paper trading against a null arm and buy-and-hold | This is the only contamination-proof test available |
| 5 | Only then chase alpha: an LLM ranker over a liquid universe, long top-N, research-tool driven | This is the one live, bias-free positive result (Sharpe 2.43), but it is a single study |
| 6 | Later: fine-tune on your own logged decisions (SFT → GRPO) | The only model-side lever left once models test as equivalent |

**Honest expectation:** steps 1–4 make Augur *lose less and know whether it
works*. No published evidence supports "win a lot of money" from LLM trading
decisions alone. Where edges exist, they are narrow, crowded, and decaying, and
they have to be proven on your own post-cutoff data.

---

## Sources

**Live and production evidence**
- [DXRG — What LLM Trading Agents Actually Do in Production (arXiv 2609.05663)](https://arxiv.org/abs/2609.05663)
- [Alpha Arena (nof1)](https://nof1.ai/) · [Season 1 results](https://www.iweaver.ai/blog/alpha-arena-ai-trading-season-1-results/) · [S1.5 Grok result](https://finance.yahoo.com/news/elon-musks-grok-4-20-123855766.html) · [all-models-lose report](https://finance.biggo.com/news/5BSX_Z0BaoGGrU-ID27J)
- [Agent Market Arena — When Agents Trade (arXiv 2510.11695)](https://arxiv.org/abs/2510.11695)
- [LiveTradeBench (arXiv 2511.03628)](https://arxiv.org/html/2511.03628v1) · [AI-Trader (arXiv 2512.10971)](https://arxiv.org/abs/2512.10971) · [PolyBench (arXiv 2604.14199)](https://arxiv.org/html/2604.14199)
- [Autonomous Market Intelligence: Agentic AI Nowcasting (arXiv 2601.11958)](https://arxiv.org/abs/2601.11958)

**Benchmarks and evaluation**
- [FINSABER (KDD 2026, arXiv 2505.07078)](https://arxiv.org/abs/2505.07078) · [StockBench (arXiv 2510.02209)](https://arxiv.org/abs/2510.02209)
- [KTD-Fin — From Knowing to Doing (arXiv 2605.28359)](https://arxiv.org/html/2605.28359v1) · [CLQT (arXiv 2606.29771)](https://arxiv.org/abs/2606.29771) · [TraderBench (arXiv 2603.00285)](https://arxiv.org/abs/2603.00285)
- [Agentic Trading survey (arXiv 2605.19337)](https://arxiv.org/abs/2605.19337) · [Agentic Quantitative Trading survey (arXiv 2608.31041)](https://arxiv.org/abs/2608.31041) · [Hedge-fund review of LLM forecasting (arXiv 2605.05211)](https://arxiv.org/html/2605.05211v1)
- [ForecastBench parity update](https://forecastingresearch.substack.com/p/ai-models-have-likely-reached-parity)

**Methods and training**
- [Trading-R1 (arXiv 2509.11420)](https://arxiv.org/abs/2509.11420) · [Alpha-R1 (arXiv 2512.23515)](https://arxiv.org/abs/2512.23515)
- Classics: Moreira & Muir, *Volatility-Managed Portfolios* (J. Finance 2017); Bailey & López de Prado, *The Deflated Sharpe Ratio* (JPM 2014); Bailey, Borwein, López de Prado & Zhu, *Probability of Backtest Overfitting* (J. Comp. Finance 2017); López de Prado, *Advances in Financial Machine Learning* (2018); Harvey, Liu & Zhu, *…and the Cross-Section of Expected Returns* (RFS 2016)

**Look-ahead bias**
- [Memorization Problem (arXiv 2504.14765)](https://arxiv.org/abs/2504.14765) · [Detecting Lookahead Bias (arXiv 2512.23847)](https://arxiv.org/abs/2512.23847) · [Look-Ahead-Bench (arXiv 2601.13770)](https://arxiv.org/abs/2601.13770) · [MemGuard-Alpha (arXiv 2603.26797)](https://arxiv.org/abs/2603.26797)

**Security and systemic risk**
- [FARSIGHT SoK (arXiv 2609.19705)](https://arxiv.org/abs/2609.19705) · [Adversarial Feeds (arXiv 2606.00914)](https://arxiv.org/abs/2606.00914) · [Market Signal Injection (arXiv 2609.18357)](https://arxiv.org/abs/2609.18357)
- [BoE warning on AI agents](https://letsdatascience.com/news/bank-of-england-warns-ai-agents-could-disrupt-markets-f9e6bfae) · [AI in Trading 2026 / SEC letter](https://www.mindfulmarkets.ai/ai-in-trading-2026-from-god-has-helped-us-and-so-will-ai-to-a-deadline-on-capitol-hill-the-frontier-model-reality-check/)

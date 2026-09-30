# Augur as a Service: Plan

**One line:** trading agents with guardrails. Augur is software that watches crypto, gold,
oil and stocks, and trades only inside hard risk rules. It starts on practice money and is
honest about whether it works.

This plan covers what to sell, what the law requires, the architecture it will need, and
a phased path with exit criteria. Legal points are flagged **(confirm with counsel)**. They
describe the landscape, not legal advice.

---

## 1. What we sell, and what we don't

| We sell | We don't sell |
|---|---|
| Software that runs a user's **own rules** in the user's **own broker account** | Promises of returns ("win $1M") |
| Guardrails: a stop on every trade, sizing, kill switch, rate limits | Custody of anyone's money or coins |
| Honest measurement: results net of costs, compared with a benchmark | Trading with money we pool from users |
| Practice-first onboarding: paper trading before any live money | Access for minors to live trading |

**Why this positioning:** the research in [RESEARCH_AGENT_TRADING_2026.md](RESEARCH_AGENT_TRADING_2026.md)
shows no published LLM trading edge that survives costs. The durable value is loss
avoidance, discipline and honesty. Those are what we can deliver and defend.

---

## 2. Regulatory map (the part that decides the business model)

| Activity | What it likely triggers | Our stance |
|---|---|---|
| Automated trading in a customer's account under our control, for a fee | **Investment adviser** status (US Investment Advisers Act of 1940). Robo-advisers are registered advisers under the SEC's 2017 guidance. SEC registration generally applies at $100M+ AUM; below that, state registration. **(confirm with counsel)** | Don't offer until registered, or until we partner with a registered adviser |
| General, impersonal market content (the Markets scan as education) | Likely within the publisher's exclusion (*Lowe v. SEC*, 1985) when impersonal and regularly published. **(confirm with counsel)** | OK for the free tier; keep it impersonal |
| Handling orders or earning per-trade fees | **Broker-dealer** registration | Never take transaction-based pay. Use a licensed broker's API. |
| Holding customer funds or crypto | Money-transmitter or custody rules; in the EU, **MiCA** crypto-asset service provider (CASP) authorization | Stay **non-custodial**: users keep assets at their broker or exchange |
| Advice on futures | CFTC commodity trading advisor (CTA) rules | Commodities only via ETFs (securities); no futures products |
| EU users | MiFID II for securities advice and portfolio management; MiCA for crypto services | US-first. EU only after authorization or a partner. |
| Marketing performance | SEC Marketing Rule for advisers, and FTC rules on deceptive claims | Show only audited, net-of-cost results with a benchmark and drawdown |
| Users under 18 | Brokers require adult account holders (Alpaca: 18+) | Paper mode only for minors; live trading needs adult KYC at the broker |

**Three compliant launch paths, from easiest to hardest:**

1. **Education and paper trading** (launch here). A free and paid tool that scans markets,
   explains setups, and trades **paper** accounts. There's no live execution for others, so the
   lowest burden.
2. **Self-directed automation.** The user writes or chooses the rules and approves the
   strategy, and the software executes the user's own instructions in the user's own account.
   The regulatory line here is fine **(confirm with counsel)**.
3. **Registered or partnered.** Register an RIA, or partner with one, and use a
   brokerage-as-a-service provider (e.g. Alpaca's Broker API, where the partner is the
   broker-dealer and custodian). Needed for "the agent manages my money".

---

## 3. Product tiers (prices are hypotheses to test)

| Tier | Who | Includes | Price to test |
|---|---|---|---|
| **Free** | Learners, students, kids with a parent | Paper trading, Markets scan (delayed or IEX data), safety rules, guided integrations | $0 |
| **Pro** | Self-directed traders | Multiple paper accounts, backtests with costs, alerts, trade journal export, wallet watching | $15–29/mo |
| **Pro Live** *(after §2 path 2 or 3)* | Adults with their own broker account | Live execution of the user's own rules, per-account kill switch, daily loss caps | $39–79/mo, flat (never per trade) |
| **Advisor** *(after registration or partner)* | RIAs | White-label, compliance exports, the decision provenance ledger | Per seat |

Charge flat subscriptions only. Per-trade pricing looks like broker compensation and rewards
overtrading, which the research identifies as the #1 loss driver.

---

## 4. From today's app to a multi-user service

**What exists now** (single user, local):
- guardrailed pipeline and risk engine
- bracket orders, broker reconciliation, kill switch, rate limits
- live prices (Alpaca), markets scan (crypto, gold, silver, oil)
- watch-only wallets, guided integrations
- 290+ automated tests

**Gaps before other people can use it:**

| Area | Today | Needed |
|---|---|---|
| Identity | none (localhost-only) | Sign-in with mandatory MFA (OIDC provider) |
| Secrets | `.env` file | Per-user secrets encrypted with a KMS or Vault; **broker OAuth** instead of pasted keys |
| State | in memory | Postgres: accounts, orders, fills, journal/provenance ledger; migrations |
| Execution | one process | A worker per account, a job queue, idempotent orders (`client_order_id`), retries with backoff |
| Reconciliation | 15s sync loop | The same logic as a durable job, plus end-of-day statement reconciliation and alerting on drift |
| Market data | user's Alpaca entitlement | Keep data under **each user's** entitlement. Redistributing exchange data to users needs vendor licensing. |
| Safety | per-process guard | Per-account **and** global kill switch, daily loss caps enforced server-side, and an anomaly halt (e.g. 3 rejected orders in a row) |
| Ops | logs to console | Structured logs, metrics, tracing, paging on any `UNPROTECTED` position, status page |
| Security | local only | Pen test, dependency scanning, least-privilege keys (trade-only, no withdrawals), a SOC 2 path once B2B |

**Design rule carried over from the research:** mechanism over exhortation. Every safety
property lives in code on the server, never in a prompt or in the browser.

---

## 5. Roadmap with exit criteria

| Phase | Weeks | Build | Exit criteria (all must hold) |
|---|---|---|---|
| **0. Harden** | 0–4 | Postgres ledger, auth, encrypted secrets, broker OAuth, CI on every push | 0 failing tests; restart loses no state; secrets never on disk in plaintext |
| **1. Paper beta** | 4–10 | Invite 25–50 users, paper only; onboarding under 10 min | ≥60% connect a paper account; 0 `UNPROTECTED` incidents; 100% of trades bracketed |
| **2. Evidence** | 10–22 | Every user's paper results vs benchmark, net of costs, with day-clustered CIs (see research §4) | A published, honest scorecard. No live launch on a Sharpe the evidence rules can't confirm. |
| **3. Legal** | parallel from week 4 | Counsel opinion on path 2 vs 3; terms, privacy, risk disclosures | Written opinion in hand before any live execution for others |
| **4. Paid** | 22+ | Pro tier (paper), then Pro Live if §2 allows | Paying users; refund rate <5%; complaint log reviewed weekly |

---

## 6. Metrics that matter

- **Safety (target 0):** positions without a stop, kill-switch failures, reconciliation drift.
- **Honesty:** share of results screens that show net-of-cost returns next to the benchmark (target 100%).
- **Activation:** time from signup to first practice trade.
- **Retention:** weekly active accounts at week 4 and week 12.
- **Behavior:** trades per user per day (lower is usually healthier), and the share of users with a daily loss cap set.

---

## 7. Costs to plan for

| Item | Driver | Note |
|---|---|---|
| Market data | Per-user entitlement vs redistribution | Redistribution licensing is the big one; avoid it at first |
| Model inference | Decisions × tokens | Frontier models tested as indistinguishable on trading decisions, with a ~25× cost spread; use the cheapest stable model |
| Infra | Workers per active account | Small at beta scale |
| Legal and compliance | Counsel, registration if path 3 | Budget before revenue |
| Security | Pen test, SOC 2 (B2B) | Needed before Advisor tier |

---

## 8. Top risks

| Risk | Mitigation |
|---|---|
| Users lose money and blame us | Paper-first gate, loss caps on by default, no return promises, plain risk disclosures |
| Regulatory action | §2 paths, counsel before live, flat pricing, no custody |
| Leaked API keys | OAuth, encrypted storage, trade-only scopes, instant revoke |
| Correlated agent behavior in stress (a concern raised by the BoE and in Congress in 2026) | Diversity of rules per user, global rate limits, market-wide halt switch |
| Hype mismatch | Market the guardrails and honesty, not the returns |

---

## 9. Brand kit

Files live in `ui/public/brand/` (plus `ui/public/favicon.svg`):

| Asset | File | Use |
|---|---|---|
| Mark (vector) | `favicon.svg` | App icon, favicon, avatars |
| Mark (512px PNG) | `brand/augur-icon-512.png` | App stores, Apple touch icon |
| Wordmark | `brand/augur-wordmark.svg` | Headers, docs (inherits text color) |
| Social card | `brand/og-card.svg` / `og-card.png` (1200×630) | Link previews |

- **Idea:** a gull over the horizon, its longer wing rising like a steady equity line.
  Augurs read the future from the flight of birds; this one also knows where the horizon is.
- **Colors:** blue `#3987e5` → `#184f95` (the mark), ink `#0b0b0b`, surface `#fcfcfb`. Status colors are reserved for good, warning and critical, and are always shown with an icon and a label.
- **Type:** system sans only (`system-ui`, Segoe UI, Roboto).
- **Voice:** calm, plain, honest. "Every trade has a stop." Never "get rich".
- **Don't:** rocket ships, lambos, money rain, or return claims.

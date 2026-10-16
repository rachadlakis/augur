"""Forward validation of the secondary signals (policy news, whale flows).

The research behind these signals is modest, so their weight has to be earned
live. Every intel refresh stores the raw readings and what the analysts made of
them; once each signal's horizon has passed, the asset's realized return over
that horizon is attached; and the calibrator the trading pipeline uses is
rebuilt from those scored outcomes. Until enough outcomes exist, the
calibrator passes the stated confidence through unchanged.

Readings are taken every 15 minutes but claim 1-24h horizons, so consecutive
readings overlap almost entirely. Only outcomes spaced at least one horizon
apart (per asset) feed the calibrator and the statistics; otherwise 50
"samples" could be one afternoon of data counted 50 times.

Storage is a local SQLite file. Rows are only ever inserted, never updated.
Stdlib-only apart from the analysts; price bars are injected by the caller.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from collections import defaultdict
from collections.abc import Callable
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .calibration import SpecialistCalibrator, _pearson
from .evaluation import probabilistic_sharpe_ratio
from .specialists import PolicyRiskAnalyst, WhaleFlowAnalyst

logger = logging.getLogger(__name__)

POLICY_AGENT = "policy_news"
WHALE_AGENT = "whale_flows"

# Horizons each signal is scored at, in hours. The primary horizon is the one
# whose outcomes calibrate the live pipeline (trades are held hours to days).
HORIZONS: dict[str, tuple[float, ...]] = {POLICY_AGENT: (24.0,), WHALE_AGENT: (1.0, 6.0)}
PRIMARY_HORIZON: dict[str, float] = {POLICY_AGENT: 24.0, WHALE_AGENT: 6.0}

# (symbol, context, safe_haven): SPY stands in for risk assets, GLD for gold.
POLICY_TARGETS: tuple[tuple[str, str, bool], ...] = (("SPY", "risk_assets", False), ("GLD", "gold", True))
WHALE_TARGETS: tuple[str, ...] = ("BTC/USD", "ETH/USD")

BAR_HOURS = 1.0
SCORE_GRACE_HOURS = 1.0  # let the bar that closes at the horizon arrive before scoring
MAX_SCORE_AGE_DAYS = 30.0  # older unscored readings are written off, not fetched forever

BarFetcher = Callable[[str, datetime], list[dict[str, Any]]]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    raw TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reading_id INTEGER NOT NULL REFERENCES readings(id),
    ts TEXT NOT NULL,
    agent TEXT NOT NULL,
    target TEXT NOT NULL,
    context TEXT NOT NULL,
    signal TEXT NOT NULL,
    confidence REAL NOT NULL,
    lean REAL,
    output TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS signals_agent_ts ON signals(agent, ts);
CREATE TABLE IF NOT EXISTS scores (
    signal_id INTEGER NOT NULL REFERENCES signals(id),
    horizon_h REAL NOT NULL,
    status TEXT NOT NULL,
    forward_return REAL,
    start_price REAL,
    end_price REAL,
    reason TEXT,
    scored_at TEXT NOT NULL,
    PRIMARY KEY (signal_id, horizon_h)
);
"""


def _iso(moment: datetime) -> str:
    """One fixed UTC format, so ISO strings sort and compare as times in SQL."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds")


def _parse(value: Any) -> datetime:
    moment = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def intel_signals(news_ctx: dict[str, Any] | None, whale_flows: dict[str, Any] | None) -> list[dict[str, Any]]:
    """What each analyst says about each tracked asset, plus a continuous `lean`
    (positive = bullish for that asset) for a rank test that includes NEUTRAL calls."""
    rows: list[dict[str, Any]] = []
    if news_ctx is not None:
        for symbol, context, safe_haven in POLICY_TARGETS:
            out = PolicyRiskAnalyst().analyze(news_ctx, safe_haven=safe_haven)
            risk_off = out.get("risk_off_score")
            lean = None if risk_off is None else (float(risk_off) if safe_haven else -float(risk_off))
            rows.append({"agent": str(out.get("agent", POLICY_AGENT)), "target": symbol, "context": context,
                         "output": out, "lean": lean})
    if whale_flows is not None:
        for symbol in WHALE_TARGETS:
            out = WhaleFlowAnalyst().analyze(whale_flows, asset=symbol)
            score = out.get("flow_score")
            rows.append({"agent": str(out.get("agent", WHALE_AGENT)), "target": symbol, "context": "crypto",
                         "output": out, "lean": None if score is None else float(score)})
    return rows


class SignalStore:
    """Append-only SQLite record of readings, signals, and their scores."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.executescript(_SCHEMA)
        return conn

    def record(self, signals: list[dict[str, Any]], raw: dict[str, Any], at: datetime | None = None) -> int:
        """Store one refresh. Returns the reading id."""
        ts = _iso(at or datetime.now(timezone.utc))
        with self._lock, closing(self._connect()) as conn, conn:
            reading_id = conn.execute(
                "INSERT INTO readings (ts, raw) VALUES (?, ?)", (ts, json.dumps(raw, default=str))
            ).lastrowid
            conn.executemany(
                "INSERT INTO signals (reading_id, ts, agent, target, context, signal, confidence, lean, output)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (reading_id, ts, row["agent"], row["target"], row["context"],
                     str(row["output"].get("signal", "NEUTRAL")).upper(), float(row["output"].get("confidence", 0.0)),
                     row.get("lean"), json.dumps(row["output"], default=str))
                    for row in signals
                ],
            )
        return int(reading_id)

    def pending(self, now: datetime, *, grace_hours: float = SCORE_GRACE_HOURS) -> list[dict[str, Any]]:
        """Signal/horizon pairs whose horizon (plus grace) has passed and that have no score yet."""
        if not self.path.exists():
            return []
        due: list[dict[str, Any]] = []
        with closing(self._connect()) as conn:
            for agent, horizons in HORIZONS.items():
                for horizon in horizons:
                    cutoff = _iso(now - timedelta(hours=horizon + grace_hours))
                    rows = conn.execute(
                        "SELECT id, ts, agent, target, signal, confidence FROM signals s"
                        " WHERE agent = ? AND ts <= ? AND NOT EXISTS"
                        " (SELECT 1 FROM scores c WHERE c.signal_id = s.id AND c.horizon_h = ?) ORDER BY ts",
                        (agent, cutoff, horizon),
                    ).fetchall()
                    due.extend({**dict(row), "horizon_h": horizon} for row in rows)
        return sorted(due, key=lambda r: (r["ts"], r["id"], r["horizon_h"]))

    def add_scores(self, scores: list[dict[str, Any]]) -> None:
        if not scores:
            return
        scored_at = _iso(datetime.now(timezone.utc))
        with self._lock, closing(self._connect()) as conn, conn:
            # OR IGNORE: a score, once written, is never replaced.
            conn.executemany(
                "INSERT OR IGNORE INTO scores (signal_id, horizon_h, status, forward_return, start_price, end_price,"
                " reason, scored_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (s["signal_id"], s["horizon_h"], s["status"], s.get("forward_return"), s.get("start_price"),
                     s.get("end_price"), s.get("reason"), scored_at)
                    for s in scores
                ],
            )

    def outcomes(self) -> list[dict[str, Any]]:
        """Every scored signal with its realized return, oldest reading first."""
        if not self.path.exists():
            return []
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT s.id AS signal_id, s.ts, s.agent, s.target, s.signal, s.confidence, s.lean, c.horizon_h,"
                " c.forward_return FROM scores c JOIN signals s ON s.id = c.signal_id"
                " WHERE c.status = 'scored' ORDER BY s.ts, s.id, c.horizon_h"
            ).fetchall()
        return [dict(row) for row in rows]

    def summary(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"readings": 0, "last_reading_at": None, "scores_by_status": {}}
        with closing(self._connect()) as conn:
            count, last = conn.execute("SELECT COUNT(*), MAX(ts) FROM readings").fetchone()
            statuses = dict(conn.execute("SELECT status, COUNT(*) FROM scores GROUP BY status").fetchall())
        return {"readings": count, "last_reading_at": last, "scores_by_status": statuses}


def price_at(bars: list[dict[str, Any]], moment: datetime, *, bar_hours: float = BAR_HOURS) -> tuple[float, datetime] | None:
    """Close of the last bar that had finished by `moment`, and when it finished.

    Bars are stamped with their start time, so a bar's close is the price at
    start + bar length. Using only finished bars keeps the future out.
    """
    best: tuple[float, datetime] | None = None
    for bar in bars:
        end = _parse(bar["timestamp"]) + timedelta(hours=bar_hours)
        if end <= moment and (best is None or end > best[1]):
            best = (float(bar["close"]), end)
    return best


def forward_return(bars: list[dict[str, Any]], start: datetime, horizon_h: float) -> dict[str, Any]:
    """Realized return from `start` to `start + horizon_h`, or why it can't be measured."""
    opening = price_at(bars, start)
    if opening is None or opening[0] <= 0:
        return {"status": "skipped", "reason": "no price at the time of the reading"}
    closing_ = price_at(bars, start + timedelta(hours=horizon_h))
    if closing_ is None or closing_[1] <= opening[1]:
        # Market closed for the whole window (weekend, holiday): a 0% "return"
        # would be scored as a wrong call, so it isn't scored at all.
        return {"status": "skipped", "reason": "no trading during the horizon"}
    return {
        "status": "scored",
        "forward_return": closing_[0] / opening[0] - 1.0,
        "start_price": opening[0],
        "end_price": closing_[0],
    }


def score_pending(store: SignalStore, fetch_bars: BarFetcher, now: datetime | None = None, *,
                  grace_hours: float = SCORE_GRACE_HOURS, max_age_days: float = MAX_SCORE_AGE_DAYS) -> list[dict[str, Any]]:
    """Score every signal whose horizon has passed. Returns the new scores.

    Bars are fetched once per asset. If a fetch fails, that asset's signals stay
    pending and are retried on the next run.
    """
    now = now or datetime.now(timezone.utc)
    by_target: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in store.pending(now, grace_hours=grace_hours):
        by_target[item["target"]].append(item)

    scores: list[dict[str, Any]] = []
    oldest_allowed = now - timedelta(days=max_age_days)
    for target, items in by_target.items():
        fresh = []
        for item in items:
            if _parse(item["ts"]) < oldest_allowed:
                scores.append({"signal_id": item["id"], "horizon_h": item["horizon_h"], "status": "skipped",
                               "reason": f"not scored within {max_age_days:g} days"})
            else:
                fresh.append(item)
        if not fresh:
            continue
        since = min(_parse(item["ts"]) for item in fresh) - timedelta(hours=2 * BAR_HOURS)
        try:
            bars = fetch_bars(target, since)
        except Exception as e:  # any feed error just means "try again next refresh"
            logger.warning(f"Signal scoring: bars for {target} unavailable: {e}")
            continue
        for item in fresh:
            result = forward_return(bars, _parse(item["ts"]), item["horizon_h"])
            scores.append({"signal_id": item["id"], "horizon_h": item["horizon_h"], **result})
    store.add_scores(scores)
    return [s for s in scores if s["status"] == "scored"]


def non_overlapping(outcomes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep outcomes at least one horizon apart per (agent, asset, horizon), oldest first."""
    last: dict[tuple[str, str, float], datetime] = {}
    kept: list[dict[str, Any]] = []
    for outcome in sorted(outcomes, key=lambda o: (o["ts"], o["signal_id"])):
        key = (outcome["agent"], outcome["target"], float(outcome["horizon_h"]))
        moment = _parse(outcome["ts"])
        if key not in last or moment - last[key] >= timedelta(hours=key[2]):
            last[key] = moment
            kept.append(outcome)
    return kept


def _rows(outcomes: list[dict[str, Any]]) -> list[tuple[str, float, float]]:
    return [(o["signal"], o["confidence"], o["forward_return"]) for o in outcomes]


def load_calibrator(store: SignalStore, calibrator: SpecialistCalibrator | None = None) -> SpecialistCalibrator:
    """Rebuild each secondary agent's history from its primary-horizon outcomes.

    Pass the live calibrator to update it in place; other agents' histories
    are left alone.
    """
    calibrator = calibrator or SpecialistCalibrator()
    thinned = non_overlapping(store.outcomes())
    for agent, horizon in PRIMARY_HORIZON.items():
        calibrator.load(agent, _rows([o for o in thinned if o["agent"] == agent and o["horizon_h"] == horizon]))
    return calibrator


def _significance(psr: float, n: int) -> str:
    if psr >= 0.95:
        return (f"Probabilistic Sharpe {psr:.2f}: following this signal beat zero with at least 95% probability over "
                f"{n} non-overlapping samples. That is one test; if several variants were tried, check the "
                "deflated Sharpe ratio before trusting it.")
    return f"Probabilistic Sharpe {psr:.2f}: not distinguishable from luck yet over {n} non-overlapping samples."


def validation_report(store: SignalStore, *, min_samples: int | None = None) -> dict[str, Any]:
    """Hit rate, information coefficient and sample count per signal and horizon."""
    min_samples = SpecialistCalibrator().min_samples if min_samples is None else min_samples
    outcomes = store.outcomes()
    thinned = non_overlapping(outcomes)
    rows: list[dict[str, Any]] = []
    for agent, horizons in HORIZONS.items():
        for horizon in horizons:
            primary = PRIMARY_HORIZON[agent] == horizon
            group = [o for o in thinned if o["agent"] == agent and o["horizon_h"] == horizon]
            calibrator = SpecialistCalibrator(min_samples=min_samples)
            calibrator.load(agent, _rows(group))
            n = calibrator.samples(agent)
            by_target: dict[str, int] = defaultdict(int)
            for o in group:
                if o["signal"] in {"BUY", "SELL"}:
                    by_target[o["target"]] += 1
            row: dict[str, Any] = {
                "agent": agent,
                "horizon_h": horizon,
                "used_by_pipeline": primary,
                "scored_readings": sum(1 for o in outcomes if o["agent"] == agent and o["horizon_h"] == horizon),
                "non_overlapping": len(group),
                "samples": n,
                "min_samples": min_samples,
                "samples_by_asset": dict(by_target),
                "hit_rate": None,
                "information_coefficient": None,
                "lean_ic": None,
                "probabilistic_sharpe": None,
                "weight": None,
            }
            if n < min_samples:
                row["status"] = "not_enough_data"
                row["message"] = (f"Not enough data yet: {n} of {min_samples} non-overlapping BUY/SELL calls scored. "
                                  + ("Until then the pipeline uses the analyst's stated confidence." if primary
                                     else "Shown for comparison only."))
            else:
                stats = calibrator.report(agent)
                strategy = [(1.0 if o["signal"] == "BUY" else -1.0) * o["forward_return"]
                            for o in group if o["signal"] in {"BUY", "SELL"}]
                leaned = [o for o in group if o["lean"] is not None]
                psr = probabilistic_sharpe_ratio(strategy)
                row.update(
                    status="ok",
                    hit_rate=stats["hit_rate"],
                    information_coefficient=stats["information_coefficient"],
                    brier=stats["brier"],
                    lean_ic=_pearson([o["lean"] for o in leaned], [o["forward_return"] for o in leaned]),
                    probabilistic_sharpe=psr,
                    weight=stats["weight"] if primary else None,
                    message=_significance(psr, n),
                )
            rows.append(row)
    return {
        "generated_at": _iso(datetime.now(timezone.utc)),
        "store": store.summary(),
        "signals": rows,
        "notes": [
            "Readings arrive every 15 minutes; only calls at least one horizon apart per asset are counted.",
            "BTC and ETH whale readings share the USDT flow, and SPY and GLD policy readings share the same "
            "news, so samples across assets are not fully independent.",
            "Secondary signals can confirm or veto a trade but never originate one, however well they score.",
        ],
    }

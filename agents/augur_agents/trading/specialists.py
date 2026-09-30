"""Specialist trading analyzers.

These are deterministic, schema-driven analyzers that return structured outputs
instead of free-form prose. They intentionally avoid hard-coded trust in any one
signal and are designed to be unit-tested with synthetic market conditions.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from .risk import RiskManager


def _abstain(agent: str, reason: str) -> dict[str, Any]:
    """Missing inputs never vote: a default BUY on empty data is a structural long bias."""
    return {
        "agent": agent,
        "signal": "NO_TRADE",
        "confidence": 0.0,
        "evidence": [reason],
        "risk_flags": ["data_missing"],
    }


class TechnicalAnalyst:
    """Multi-timeframe trend read that can say BUY, SELL, or NEUTRAL.

    Each bar votes by the sign of its open-to-close move; higher timeframes
    weigh more because short-horizon moves tend to reverse. A direction needs
    a weighted agreement of at least `min_agreement`.
    """

    TIMEFRAME_WEIGHTS = {"15m": 0.5, "1h": 1.0, "4h": 1.5, "1d": 2.0}

    def __init__(
        self,
        *,
        stop_atr_multiple: float = 2.0,
        target_atr_multiple: float = 4.0,
        min_agreement: float = 0.5,
        deadband: float = 0.001,
    ) -> None:
        self.stop_atr_multiple = stop_atr_multiple
        self.target_atr_multiple = target_atr_multiple
        self.min_agreement = min_agreement
        self.deadband = deadband

    def trend_score(self, ohlcv: dict[str, dict[str, float]]) -> tuple[float, dict[str, int]]:
        """Weighted vote in [-1, 1] and each timeframe's vote (+1 up, -1 down, 0 flat)."""
        votes: dict[str, int] = {}
        weighted = total = 0.0
        for timeframe, weight in self.TIMEFRAME_WEIGHTS.items():
            bar = ohlcv.get(timeframe) or {}
            open_price = float(bar.get("open", 0.0) or 0.0)
            close_price = float(bar.get("close", 0.0) or 0.0)
            if open_price <= 0 or close_price <= 0:
                continue
            move = close_price / open_price - 1.0
            vote = 0 if abs(move) < self.deadband else (1 if move > 0 else -1)
            votes[timeframe] = vote
            weighted += weight * vote
            total += weight
        return (weighted / total if total else 0.0), votes

    def analyze(self, snapshot: Any) -> dict[str, Any]:
        price = float(getattr(snapshot, "price", 0.0) or 0.0)
        ohlcv = getattr(snapshot, "ohlcv", {}) or {}
        volatility = getattr(snapshot, "volatility", {}) or {}
        atr = float(volatility.get("atr", 0.0) or 0.0)
        if not ohlcv:
            return _abstain("technical", "missing OHLCV")
        if price <= 0 or atr <= 0:
            return _abstain("technical", "missing price or ATR; stops cannot be volatility-scaled")

        score, votes = self.trend_score(ohlcv)
        if not votes:
            return _abstain("technical", "no usable open/close bars")
        if score >= self.min_agreement:
            signal, trend = "BUY", "uptrend"
        elif score <= -self.min_agreement:
            signal, trend = "SELL", "downtrend"
        else:
            signal, trend = "NEUTRAL", "mixed"

        # Conviction falls as volatility rises: realized P&L degrades with entry volatility.
        atr_fraction = atr / price
        confidence = min(0.7, max(0.3, 0.7 - atr_fraction * 5.0)) * abs(score)
        levels = RiskManager.bracket_levels(
            entry=price,
            atr=atr,
            side="SELL" if signal == "SELL" else "BUY",
            stop_multiple=self.stop_atr_multiple,
            target_multiple=self.target_atr_multiple,
        )
        direction = -1.0 if signal == "SELL" else 1.0
        risk_flags = ["high_volatility"] if atr_fraction > 0.05 else []
        return {
            "agent": "technical",
            "signal": signal,
            "confidence": round(float(confidence), 4),
            "time_horizon": "4h-24h",
            "trend_score": round(score, 4),
            "timeframe_votes": votes,
            "entry_zone": {"lower": price - 0.5 * atr, "upper": price + 0.5 * atr},
            "stop_level": levels["stop"],
            "target_zone": {"min": levels["target"], "max": price + direction * (self.target_atr_multiple + 1.0) * atr},
            "trend": trend,
            "momentum": {"uptrend": "positive", "downtrend": "negative"}.get(trend, "mixed"),
            "volatility": "high" if risk_flags else "moderate",
            "support_resistance": {"support": price - atr, "resistance": price + atr},
            "evidence": [
                f"weighted timeframe agreement {score:+.2f} from {votes}",
                f"stop and target are {self.stop_atr_multiple:g}x / {self.target_atr_multiple:g}x ATR",
            ],
            "invalidation_reason": "higher-timeframe bars flip against the trend",
            "risk_flags": risk_flags,
        }


class OnChainAnalyst:
    def analyze(self, metrics: dict[str, Any]) -> dict[str, Any]:
        if not metrics:
            return _abstain("onchain", "no on-chain metrics supplied")
        netflow = float(metrics.get("netflow", 0.0) or 0.0)
        transfer_type = metrics.get("transfer_classification", "unknown")
        if transfer_type == "unknown":
            interpretation = "On-chain flow is ambiguous; cannot distinguish exchange-internal transfers from genuine market flows."
            signal = "HOLD"
        else:
            interpretation = f"Observed {transfer_type} flow pattern with netflow {netflow}."
            signal = "BUY" if netflow > 0 else "SELL"

        return {
            "agent": "onchain",
            "signal": signal,
            "confidence": 0.6,
            "flow_direction": "positive" if netflow > 0 else "negative",
            "anomaly_flags": [],
            "key_metric_values": metrics,
            "evidence": [interpretation],
            "interpretation": interpretation,
            "invalidation_reason": "transfer classification changes or netflow reverses without supporting price action",
        }


class NewsSentimentAnalyst:
    """Scores structured news events; free text never reaches the score.

    Events are canonicalized first: sentiment must be numeric and is clamped
    to [-1, 1], impact labels outside the known set count as low, duplicates
    and stale items are dropped, and every other field (headline, body, URL)
    is ignored. One-sided floods from low-credibility sources, the pattern
    adversarial feeds use to tip uncertain agents, are flagged and discounted.
    """

    CREDIBLE_SOURCES = {"official", "exchange", "central_bank", "newswire"}
    IMPACT_LEVELS = {"HIGH_IMPACT", "MEDIUM_IMPACT", "LOW_IMPACT"}

    def __init__(self, *, max_age_hours: float = 24.0) -> None:
        self.max_age_hours = max_age_hours

    def canonicalize(self, events: list[dict[str, Any]], now: datetime | None = None) -> list[dict[str, Any]]:
        now = now or datetime.now(timezone.utc)
        seen: set[str] = set()
        clean: list[dict[str, Any]] = []
        for event in events:
            try:
                sentiment = float(event.get("sentiment"))
            except (TypeError, ValueError):
                continue  # no numeric score: nothing to trust
            if math.isnan(sentiment):
                continue
            published = event.get("published")
            if isinstance(published, datetime):
                if published.tzinfo is None:
                    published = published.replace(tzinfo=timezone.utc)
                if (now - published).total_seconds() > self.max_age_hours * 3600:
                    continue
            key = str(event.get("headline", "")).strip().lower()
            if key and key in seen:
                continue
            seen.add(key)
            impact = str(event.get("impact", "")).upper()
            clean.append({
                "source": str(event.get("source", "")).strip().lower(),
                "sentiment": max(-1.0, min(1.0, sentiment)),
                "impact": impact if impact in self.IMPACT_LEVELS else "LOW_IMPACT",
            })
        return clean

    def analyze(self, events: list[dict[str, Any]], now: datetime | None = None) -> dict[str, Any]:
        events = self.canonicalize(events, now)
        if not events:
            return {"agent": "sentiment_news", "signal": "NEUTRAL", "confidence": 0.0, "narrative": "no material news", "source_credibility": 0.0, "impact_score": 0.0, "novelty_score": 0.0, "manipulation_flags": [], "evidence": []}

        weighted = 0.0
        credibility = 0.0
        impact_score = 0.0
        novelty = 0.0
        for event in events:
            source_weight = 1.0 if event["source"] in self.CREDIBLE_SOURCES else 0.5
            weighted += event["sentiment"] * source_weight
            credibility += source_weight
            impact_score += 0.5 if event["impact"] in {"HIGH_IMPACT", "MEDIUM_IMPACT"} else 0.2
            novelty += 0.5 if event["impact"] == "HIGH_IMPACT" else 0.2

        manipulation_flags: list[str] = []
        low_cred = [e for e in events if e["source"] not in self.CREDIBLE_SOURCES]
        if len(events) >= 3 and len(low_cred) / len(events) >= 0.7:
            signs = {1 if e["sentiment"] > 0 else -1 if e["sentiment"] < 0 else 0 for e in low_cred}
            if len(signs - {0}) == 1:
                manipulation_flags.append("one_sided_low_credibility_feed")

        signal = "BUY" if weighted > 0 else "SELL" if weighted < 0 else "NEUTRAL"
        confidence = min(0.9, max(0.2, abs(weighted) / max(1.0, len(events))))
        if manipulation_flags:
            confidence = min(confidence, 0.2)
        return {
            "agent": "sentiment_news",
            "signal": signal,
            "confidence": confidence,
            "narrative": "news flow is consistent with the current tape, but social run-off remains secondary evidence",
            "source_credibility": min(1.0, credibility / max(1.0, len(events))),
            "impact_score": min(1.0, impact_score / max(1.0, len(events))),
            "novelty_score": min(1.0, novelty / max(1.0, len(events))),
            "manipulation_flags": manipulation_flags,
            "risk_flags": ["conflict"] if manipulation_flags else [],
            "evidence": ["Credible sources are weighted above anonymous chatter", "social data is treated as early signal only"],
        }


class DerivativesAnalyst:
    def analyze(self, metrics: dict[str, Any]) -> dict[str, Any]:
        if not any(key in metrics for key in ("funding_rate", "open_interest", "basis")):
            return _abstain("derivatives", "no funding, open interest, or basis data supplied")
        funding = float(metrics.get("funding_rate", 0.0) or 0.0)
        oi = float(metrics.get("open_interest", 0.0) or 0.0)
        basis = float(metrics.get("basis", 0.0) or 0.0)
        crowding_score = float(metrics.get("crowding_score", 0.0) or 0.0)
        liquidation_risk = float(metrics.get("liquidation_risk", 0.0) or 0.0)

        risk_flags = []
        if crowding_score > 0.7 or liquidation_risk > 0.7:
            risk_flags.append("crowding_risk")
        if funding > 0.0005:
            risk_flags.append("extreme_funding")

        # Symmetric: positioning confirms a direction only when basis and funding agree.
        if basis > 0 and oi > 0 and funding > 0.0005:
            signal = "HOLD"
        elif crowding_score > 0.8:
            signal = "NEUTRAL"
        elif basis > 0 and funding >= 0:
            signal = "BUY"
        elif basis < 0 and funding <= 0:
            signal = "SELL"
        else:
            signal = "NEUTRAL"

        return {
            "agent": "derivatives",
            "signal": signal,
            "confidence": 0.7,
            "funding": funding,
            "open_interest": oi,
            "basis": basis,
            "liquidation_risk": liquidation_risk,
            "crowding_score": crowding_score,
            "evidence": ["Funding and open interest are interpreted as trend confirmation and crowding risk, not automatic bearishness"],
            "risk_flags": risk_flags,
        }


class MacroAnalyst:
    GOLD_REAL_YIELD_BAND_BPS = 10.0

    def analyze(self, data: dict[str, Any]) -> dict[str, Any]:
        if data.get("underlying") == "gold" and "real_yield_change_bps" in data:
            return self._gold(data)
        if "dxy" not in data and "fed_message" not in data:
            return _abstain("macro", "no DXY or Fed data supplied")
        horizon_hours = int(data.get("horizon_hours", 24) or 24)
        dxy = float(data.get("dxy", 100.0) or 100.0)
        fed_message = str(data.get("fed_message", "neutral")).lower()

        if horizon_hours <= 6:
            signal = "NEUTRAL"
            regime = "short-horizon microstructure"
        elif dxy > 105 and "hawkish" in fed_message:
            signal = "SELL"
            regime = "risk-off macro"
        elif dxy < 100 and "dovish" in fed_message:
            signal = "BUY"
            regime = "risk-on macro"
        else:
            signal = "NEUTRAL"
            regime = "mixed macro"

        return {
            "agent": "macro",
            "signal": signal,
            "confidence": 0.55,
            "regime": regime,
            "key_events": [fed_message],
            "market_impact": 0.5,
            "evidence": ["Macro tone is weighted by holding horizon and only acts as a secondary filter"],
        }


    def _gold(self, data: dict[str, Any]) -> dict[str, Any]:
        """Gold pays no coupon, so its main macro driver is the real yield it competes with.

        Rising 10-year real (TIPS) yields have historically pushed gold down and
        falling ones pushed it up (Erb & Harvey, "The Golden Dilemma", 2013).
        Moves inside +/-10 bps over the lookback are treated as noise.
        """
        change = float(data.get("real_yield_change_bps", 0.0) or 0.0)
        band = self.GOLD_REAL_YIELD_BAND_BPS
        if change > band:
            signal, regime = "SELL", "real yields rising"
        elif change < -band:
            signal, regime = "BUY", "real yields falling"
        else:
            signal, regime = "NEUTRAL", "real yields flat"
        confidence = min(0.6, 0.3 + abs(change) / 100.0) if signal != "NEUTRAL" else 0.0
        return {
            "agent": "macro",
            "signal": signal,
            "confidence": round(confidence, 4),
            "regime": regime,
            "key_events": [f"10y real yield {change:+.0f} bps"],
            "market_impact": 0.5,
            "evidence": ["Gold moves inversely to real yields; the dollar is a secondary driver"],
        }


class TermStructureAnalyst:
    """Commodity futures curve: what an ETF holder earns or loses rolling contracts.

    Commodity ETFs such as USO hold futures and must roll them. In contango
    (later contracts dearer) every roll sells low and buys high, a steady drag
    on longs; in backwardation the roll pays. The term-structure "basis" is a
    documented commodity return factor (Erb & Harvey 2006; Szymanowska et al.
    2014). Physically backed funds (GLD, IAU) do not roll, so their curve is
    informational only and never votes.
    """

    STEEP_ANNUALIZED = 0.10  # beyond +/-10%/yr roll yield the curve takes a side

    def analyze(self, curve: dict[str, Any]) -> dict[str, Any]:
        front = float(curve.get("front_price", 0.0) or 0.0)
        next_ = float(curve.get("next_price", 0.0) or 0.0)
        days = float(curve.get("days_between", 0.0) or 0.0)
        if front <= 0 or next_ <= 0 or days <= 0:
            return _abstain("term_structure", "no futures curve supplied")

        # Annualized roll yield for a long holder: positive in backwardation.
        roll_yield = (front / next_ - 1.0) * 365.0 / days
        shape = "backwardation" if roll_yield > 0 else "contango" if roll_yield < 0 else "flat"
        risk_flags = ["contango_roll_drag"] if roll_yield < -self.STEEP_ANNUALIZED else []

        if curve.get("physically_backed"):
            signal, confidence = "NEUTRAL", 0.0
        elif roll_yield > self.STEEP_ANNUALIZED:
            signal, confidence = "BUY", min(0.6, 0.3 + roll_yield)
        elif roll_yield < -self.STEEP_ANNUALIZED:
            signal, confidence = "SELL", min(0.6, 0.3 - roll_yield)
        else:
            signal, confidence = "NEUTRAL", 0.0

        return {
            "agent": "term_structure",
            "signal": signal,
            "confidence": round(confidence, 4),
            "curve_shape": shape,
            "roll_yield_annualized": round(roll_yield, 4),
            "evidence": [f"{shape}: long holders earn {roll_yield:+.1%}/yr from rolling futures"],
            "risk_flags": risk_flags,
        }


class FundamentalsAnalyst:
    def analyze(self, data: dict[str, Any]) -> dict[str, Any]:
        if "earnings_growth" not in data and "revenue_growth" not in data:
            return _abstain("fundamentals", "no earnings or revenue data supplied")
        earnings_growth = float(data.get("earnings_growth", 0.0) or 0.0)
        revenue_growth = float(data.get("revenue_growth", 0.0) or 0.0)
        pe_relative = float(data.get("pe_relative_to_sector", 1.0) or 1.0)
        guidance = str(data.get("guidance", "neutral")).lower()
        insider_activity = str(data.get("insider_activity", "neutral")).lower()

        # Validate earnings growth is reasonable
        if earnings_growth > 100:  # absurd growth rate likely forecasting error
            return {
                "agent": "fundamentals",
                "signal": "NEUTRAL",
                "confidence": 0.3,
                "reason": "earnings forecast appears unreliable",
                "evidence": ["Extreme earnings growth projections suggest forecast quality issue"],
                "risk_flags": ["low_quality_data"],
            }

        signal = "HOLD"
        confidence = 0.5
        if earnings_growth > 15 and revenue_growth > 10 and guidance == "raised":
            signal = "BUY"
            confidence = 0.8
        elif earnings_growth < -5 and guidance == "lowered":
            signal = "SELL"
            confidence = 0.7
        elif pe_relative > 1.5:  # expensive vs peers
            signal = "SELL" if earnings_growth < 5 else "HOLD"
            confidence = 0.6

        return {
            "agent": "fundamentals",
            "signal": signal,
            "confidence": min(1.0, confidence),
            "earnings_growth": earnings_growth,
            "revenue_growth": revenue_growth,
            "pe_relative": pe_relative,
            "guidance_trend": guidance,
            "insider_activity": insider_activity,
            "evidence": [
                "Earnings and revenue trends drive long-term equity value",
                "Valuation relative to sector peers determines entry quality",
                "Insider buying/selling provides additional conviction signal",
            ],
            "risk_flags": [],
        }

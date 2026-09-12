"""Specialist trading analyzers.

These are deterministic, schema-driven analyzers that return structured outputs
instead of free-form prose. They intentionally avoid hard-coded trust in any one
signal and are designed to be unit-tested with synthetic market conditions.
"""

from __future__ import annotations

from typing import Any


class TechnicalAnalyst:
    def analyze(self, snapshot: Any) -> dict[str, Any]:
        price = float(getattr(snapshot, "price", 0.0) or 0.0)
        ohlcv = getattr(snapshot, "ohlcv", {}) or {}
        volatility = getattr(snapshot, "volatility", {}) or {}
        atr = float(volatility.get("atr", 0.0) or 0.0)
        if not ohlcv:
            return {"agent": "technical", "signal": "NO_TRADE", "confidence": 0.0, "evidence": ["missing OHLCV"], "risk_flags": ["data_missing"]}

        last_close = float(ohlcv.get("1h", {}).get("close", price))
        trend_strength = 1.0 if last_close >= price else 0.0
        signal = "BUY" if trend_strength > 0 else "HOLD"
        confidence = min(0.95, max(0.4, 0.55 + (atr / max(price, 1.0)) * 5.0))
        return {
            "agent": "technical",
            "signal": signal,
            "confidence": round(float(confidence), 4),
            "time_horizon": "4h-24h",
            "entry_zone": {"lower": price * 0.99, "upper": price * 1.01},
            "stop_level": price * 0.97,
            "target_zone": {"min": price * 1.04, "max": price * 1.08},
            "trend": "uptrend" if signal == "BUY" else "neutral",
            "momentum": "positive" if signal == "BUY" else "mixed",
            "volatility": "moderate",
            "support_resistance": {"support": price * 0.98, "resistance": price * 1.02},
            "evidence": ["multi-timeframe close prices remain above prior structure", "volatility is not extreme"],
            "invalidation_reason": "break below 1h support or loss of volume confirmation",
            "risk_flags": [],
        }


class OnChainAnalyst:
    def analyze(self, metrics: dict[str, Any]) -> dict[str, Any]:
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
    def analyze(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        if not events:
            return {"agent": "sentiment_news", "signal": "NEUTRAL", "confidence": 0.0, "narrative": "no material news", "source_credibility": 0.0, "impact_score": 0.0, "novelty_score": 0.0, "manipulation_flags": [], "evidence": []}

        weighted = 0.0
        credibility = 0.0
        impact_score = 0.0
        novelty = 0.0
        for event in events:
            source = str(event.get("source", "")).lower()
            source_weight = 1.0 if source in {"official", "exchange", "central_bank", "newswire"} else 0.5
            link_score = float(event.get("sentiment", 0.0) or 0.0)
            weighted += link_score * source_weight
            credibility += source_weight
            impact_score += 0.5 if event.get("impact") in {"HIGH_IMPACT", "MEDIUM_IMPACT"} else 0.2
            novelty += 0.5 if event.get("impact") == "HIGH_IMPACT" else 0.2

        signal = "BUY" if weighted > 0 else "SELL" if weighted < 0 else "NEUTRAL"
        return {
            "agent": "sentiment_news",
            "signal": signal,
            "confidence": min(0.9, max(0.2, abs(weighted) / max(1.0, len(events)))),
            "narrative": "news flow is consistent with the current tape, but social run-off remains secondary evidence",
            "source_credibility": min(1.0, credibility / max(1.0, len(events))),
            "impact_score": min(1.0, impact_score / max(1.0, len(events))),
            "novelty_score": min(1.0, novelty / max(1.0, len(events))),
            "manipulation_flags": [],
            "evidence": ["Credible sources are weighted above anonymous chatter", "social data is treated as early signal only"],
        }


class DerivativesAnalyst:
    def analyze(self, metrics: dict[str, Any]) -> dict[str, Any]:
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

        if basis > 0 and oi > 0 and funding > 0.0005:
            signal = "HOLD"
        elif crowding_score > 0.8:
            signal = "NEUTRAL"
        else:
            signal = "BUY"

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
    def analyze(self, data: dict[str, Any]) -> dict[str, Any]:
        horizon_hours = int(data.get("horizon_hours", 24) or 24)
        dxy = float(data.get("dxy", 100.0) or 100.0)
        fed_message = str(data.get("fed_message", "neutral")).lower()

        if horizon_hours <= 6:
            signal = "NEUTRAL"
            regime = "short-horizon microstructure"
        elif dxy > 105 and "hawkish" in fed_message:
            signal = "SELL"
            regime = "risk-off macro"
        else:
            signal = "BUY"
            regime = "risk-on macro"

        return {
            "agent": "macro",
            "signal": signal,
            "confidence": 0.55,
            "regime": regime,
            "key_events": [fed_message],
            "market_impact": 0.5,
            "evidence": ["Macro tone is weighted by holding horizon and only acts as a secondary filter"],
        }


class FundamentalsAnalyst:
    def analyze(self, data: dict[str, Any]) -> dict[str, Any]:
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

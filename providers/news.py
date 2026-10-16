"""
Politics and economics news, reduced to numbers before anything trades on it.

Three free sources, none of which hands the pipeline free text:

* GDELT DOC 2.0 (no key): the average tone of worldwide English coverage of a
  handful of market-moving themes (rates, inflation, trade, conflict,
  recession). Tone is averaged over thousands of outlets, so one fake story
  can't move it, and headlines never reach the strategy.
* FRED `USEPUINDXD` (FRED key): the daily Economic Policy Uncertainty index of
  Baker, Bloom & Davis, built from newspaper coverage of policy uncertainty.
  High readings have historically come with lower, more volatile returns.
* Federal Reserve press releases (RSS, no key): when the last FOMC statement
  or minutes came out. Prices whip around just after; entries wait.

Provenance is set here, by the code that made the request, never read from a
payload, so a feed can't promote itself to "official".
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from statistics import fmean
from typing import Any, Callable

from providers import fred
from providers.base import DataUnavailable

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
# GDELT asks for at most one request every 5 seconds per client.
GDELT_MIN_INTERVAL_SECONDS = 5.5
FED_MONETARY_RSS = "https://www.federalreserve.gov/feeds/press_monetary.xml"
EPU_SERIES = "USEPUINDXD"

# Themes that move rates, risk appetite and safe havens. Each is one GDELT query.
THEMES: dict[str, str] = {
    "rates": '("interest rates" OR "federal reserve" OR "rate hike" OR "rate cut")',
    "inflation": '(inflation OR "consumer prices" OR "price index")',
    "trade": '(tariffs OR "trade war" OR sanctions OR embargo)',
    "conflict": '(war OR invasion OR missile OR "military strike")',
    "recession": '(recession OR layoffs OR unemployment OR "economic slowdown")',
}

Opener = Callable[..., Any]
_last_gdelt_call = 0.0


class RateLimited(DataUnavailable):
    """GDELT asked us to slow down. Further calls this round would only extend the penalty."""


def _get(url: str, opener: Opener, timeout: float = 20.0) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "augur-dashboard/1.0"})
    with opener(request, timeout=timeout) as response:
        return response.read()


def _gdelt_wait(sleep: Callable[[float], None]) -> None:
    global _last_gdelt_call
    wait = GDELT_MIN_INTERVAL_SECONDS - (time.monotonic() - _last_gdelt_call)
    if wait > 0:
        sleep(wait)
    _last_gdelt_call = time.monotonic()


def theme_tone(
    query: str, *, days: int = 7, recent_hours: int = 24,
    opener: Opener = urllib.request.urlopen, sleep: Callable[[float], None] = time.sleep,
) -> dict[str, float]:
    """Average tone of the last `recent_hours` of coverage against the days before.

    GDELT tone runs roughly -10 (hostile) to +10 (glowing); news averages a
    little below zero, so the shift against the theme's own baseline is what
    carries information, not the level.
    """
    params = urllib.parse.urlencode({
        "query": f"{query} sourcelang:english", "mode": "timelinetone", "format": "json", "timespan": f"{days}d",
    })
    _gdelt_wait(sleep)
    try:
        raw = _get(f"{GDELT_URL}?{params}", opener)
        payload = json.loads(raw)
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise RateLimited("GDELT is rate-limiting this network (HTTP 429)") from e
        raise DataUnavailable(f"GDELT request failed: {e}") from e
    except ValueError as e:
        # GDELT also answers rate-limited clients with a plain-text notice instead of JSON.
        raise RateLimited(f"GDELT returned no data (rate-limited): {raw[:60]!r}") from e
    except Exception as e:
        raise DataUnavailable(f"GDELT request failed: {e}") from e

    points: list[tuple[datetime, float]] = []
    for series in payload.get("timeline") or []:
        for point in series.get("data") or []:
            try:
                when = datetime.strptime(str(point["date"]), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
                points.append((when, float(point["value"])))
            except (KeyError, TypeError, ValueError):
                continue
    if len(points) < 4:
        raise DataUnavailable("GDELT returned too little tone history")

    points.sort()
    cutoff = points[-1][0].timestamp() - recent_hours * 3600
    recent = [v for t, v in points if t.timestamp() > cutoff]
    baseline = [v for t, v in points if t.timestamp() <= cutoff]
    if not recent or not baseline:
        raise DataUnavailable("GDELT tone history doesn't cover both windows")
    return {"tone": round(fmean(recent), 4), "baseline": round(fmean(baseline), 4), "shift": round(fmean(recent) - fmean(baseline), 4)}


def all_theme_tones(opener: Opener = urllib.request.urlopen, sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    """Tone per theme; a theme GDELT won't answer is reported, never guessed."""
    tones: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for name, query in THEMES.items():
        try:
            tones[name] = theme_tone(query, opener=opener, sleep=sleep)
        except RateLimited as e:
            # Back off for this round; the next scheduled refresh tries again.
            for skipped in THEMES:
                if skipped not in tones:
                    errors[skipped] = f"{e}; retrying at the next refresh"
            break
        except DataUnavailable as e:
            errors[name] = str(e)
    return {"themes": tones, "errors": errors}


def policy_uncertainty(api_key: str, opener: Opener = urllib.request.urlopen) -> dict[str, float]:
    """Latest week of the daily EPU index and its percentile within the last year."""
    values = fred.observations(EPU_SERIES, api_key, limit=400, opener=opener)  # newest first
    if len(values) < 60:
        raise DataUnavailable("not enough policy-uncertainty history")
    week = fmean(values[:7])  # the daily series is noisy; a week is the reading
    year = values[:365]
    percentile = sum(1 for v in year if v <= week) / len(year)
    return {"latest": round(values[0], 2), "week_mean": round(week, 2), "percentile_1y": round(percentile, 4)}


def fed_events(now: datetime | None = None, opener: Opener = urllib.request.urlopen) -> dict[str, Any]:
    """Hours since the last FOMC statement or minutes, from the Fed's own feed."""
    now = now or datetime.now(timezone.utc)
    try:
        root = ET.fromstring(_get(FED_MONETARY_RSS, opener))
    except Exception as e:
        raise DataUnavailable(f"Fed press feed unavailable: {e}") from e

    releases = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        try:
            published = parsedate_to_datetime((item.findtext("pubDate") or "").strip())
        except (TypeError, ValueError):
            continue
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        lowered = title.lower()
        if "fomc statement" in lowered or "minutes of the federal open market committee" in lowered:
            releases.append({"title": title, "published": published.isoformat(),
                             "hours_ago": round((now - published).total_seconds() / 3600, 2)})
    releases.sort(key=lambda r: r["hours_ago"])
    return {"latest_fomc_hours_ago": releases[0]["hours_ago"] if releases else None, "releases": releases[:5]}


def macro_news_context(fred_key: str = "", *, opener: Opener = urllib.request.urlopen,
                       sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    """Everything the policy analyst reads, each source failing on its own."""
    context: dict[str, Any] = {"as_of": datetime.now(timezone.utc).isoformat(), "errors": {}}
    tones = all_theme_tones(opener=opener, sleep=sleep)
    context["themes"] = tones["themes"]
    context["errors"].update({f"gdelt:{k}": v for k, v in tones["errors"].items()})
    if fred_key:
        try:
            context["epu"] = policy_uncertainty(fred_key, opener=opener)
        except DataUnavailable as e:
            context["errors"]["epu"] = str(e)
    else:
        context["errors"]["epu"] = "FRED key not configured"
    try:
        events = fed_events(opener=opener)
        context["fomc_hours_ago"] = events["latest_fomc_hours_ago"]
        context["fed_releases"] = events["releases"]
    except DataUnavailable as e:
        context["errors"]["fed"] = str(e)
    return context

"""
Print how the secondary signals (policy news, whale flows) have scored against
realized returns. Reads the store the dashboard's intel loop writes; makes no
network calls.

Usage: uv run python scripts/signal_report.py [--json]
"""

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agents"))

from augur_agents.trading.signal_validation import SignalStore, validation_report  # noqa: E402


def _pct(value):
    return "-" if value is None else f"{value:.1%}"


def _num(value, fmt="+.3f"):
    return "-" if value is None else format(value, fmt)


def main() -> None:
    data_dir = Path(os.environ.get("AUGUR_DATA_DIR") or ROOT / "data")
    report = validation_report(SignalStore(data_dir / "signal_validation.sqlite3"))
    if "--json" in sys.argv:
        print(json.dumps(report, indent=2))
        return
    store = report["store"]
    print(f"{store['readings']} readings stored, last at {store['last_reading_at'] or 'never'}; "
          f"scores: {store['scores_by_status'] or 'none yet'}\n")
    print(f"{'signal':<12} {'horizon':>7} {'samples':>9} {'hit rate':>9} {'IC':>7} {'lean IC':>8} {'PSR':>5} {'weight':>7}")
    for row in report["signals"]:
        print(f"{row['agent']:<12} {row['horizon_h']:>6g}h {row['samples']:>4}/{row['min_samples']:<4} "
              f"{_pct(row['hit_rate']):>9} {_num(row['information_coefficient']):>7} {_num(row['lean_ic']):>8} "
              f"{_num(row['probabilistic_sharpe'], '.2f'):>5} {_num(row['weight'], '.2f'):>7}")
        print(f"  {row['message']}")
    print()
    for note in report["notes"]:
        print(f"- {note}")


if __name__ == "__main__":
    main()

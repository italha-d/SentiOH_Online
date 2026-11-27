from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ingestion.fsai_refresh import refresh_fsai_snapshot


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--from-date",
        default=(date.today() - timedelta(days=60)).isoformat(),
    )
    parser.add_argument(
        "--to-date",
        default=date.today().isoformat(),
    )
    parser.add_argument("--max-pages", type=int, default=10)
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument("--show-browser", action="store_true")
    args = parser.parse_args()

    result = refresh_fsai_snapshot(
        ROOT,
        from_date=args.from_date,
        to_date=args.to_date,
        max_pages=args.max_pages,
        delay=args.delay,
        show_browser=args.show_browser,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

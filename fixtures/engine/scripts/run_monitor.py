#!/usr/bin/env python3
"""Frozen PIT replay with the same CLI as momentum-tail-risk-monitor.

This is not that package and does not read parquet panels. For as-of dates
that have a vendored structured_snapshot.json it writes that JSON to
--output-json so engine_query can attach delivery_contract V_D pass.
Unknown dates exit 2 (fail closed to snapshot / local_dm / mock).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def snapshot_path(as_of: str) -> Path:
    return ROOT / "outputs" / f"snapshot_{as_of}" / "structured_snapshot.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Frozen momentum PIT replay")
    parser.add_argument("--as-of-date", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--compare-to-date", default=None)
    parser.add_argument("--evidence-cutoff", default=None)
    parser.add_argument("--horizon-days", type=int, default=20)
    args = parser.parse_args()
    as_of = args.as_of_date[:10]
    source = snapshot_path(as_of)
    if not source.is_file():
        print(f"no frozen snapshot for as_of={as_of}", file=sys.stderr)
        return 2
    out = Path(args.output_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

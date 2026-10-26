"""Generate the frontend copy of the single authored taxonomy. --check makes CI drift visible."""

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "backend/app/data/technical-careers.json"
TARGET = ROOT / "jianli/src/lib/technical-careers.json"

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    data = SOURCE.read_bytes().replace(b"\r\n", b"\n")
    if args.check:
        if not TARGET.exists() or TARGET.read_bytes().replace(b"\r\n", b"\n") != data:
            raise SystemExit(
                "Frontend taxonomy is stale; run python scripts/sync_technical_careers.py"
            )
    else:
        TARGET.write_bytes(data)

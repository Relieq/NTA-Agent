"""CLI entrypoint: `python -m nta_agent` runs the operational spine."""
from __future__ import annotations

import argparse
import sys

from nta_agent.io.api.session import TokenChainBroken
from nta_agent.runtime import runner
from nta_agent.runtime.config import ConfigError, RuntimeConfig


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="nta_agent", description="Run the NTA agent spine.")
    ap.add_argument("--ticks", type=int, default=0, help="number of ticks (0 = forever)")
    ap.add_argument("--once", action="store_true", help="run a single tick then exit")
    args = ap.parse_args(argv)
    ticks = 1 if args.once else args.ticks
    try:
        cfg = RuntimeConfig.from_env()
    except ConfigError as e:
        sys.stderr.write(f"config error: {e}\n")
        return 2
    try:
        runner.run(cfg, ticks=ticks)
    except TokenChainBroken:
        sys.stderr.write("fatal: account token chain broken and refresh failed\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

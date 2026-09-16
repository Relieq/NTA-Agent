"""CLI: `python -m nta_agent.dashboard` serves the monitoring dashboard."""
from __future__ import annotations

import argparse
import os
import sys

from nta_agent.dashboard.server import serve
from nta_agent.runtime.config import ConfigError, RuntimeConfig


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="nta_agent.dashboard", description="NTA monitoring dashboard.")
    from nta_agent.env import load_dotenv
    load_dotenv()
    ap.add_argument("--port", type=int, default=int(os.environ.get("NTA_DASHBOARD_PORT", "8787")))
    args = ap.parse_args(argv)
    try:
        cfg = RuntimeConfig.from_env()
    except ConfigError as e:
        sys.stderr.write(f"config error: {e}\n")
        return 2
    srv = serve(cfg, args.port)
    port = srv.server_address[1]
    sys.stdout.write(f"dashboard on http://127.0.0.1:{port}\n")
    sys.stdout.flush()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

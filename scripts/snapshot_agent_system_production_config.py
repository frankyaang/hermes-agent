#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent_system.production_config_snapshot import (
    load_production_config_snapshot,
    write_production_config_snapshot,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Write redacted Agent-System production config snapshot")
    parser.add_argument("--hermes-home", default=str(Path.home() / ".hermes"))
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument("--config-path", default="")
    args = parser.parse_args()

    hermes_home = Path(args.hermes_home).expanduser()
    repo_root = Path(args.repo_root).expanduser()
    config_path = Path(args.config_path).expanduser() if args.config_path else None
    path = write_production_config_snapshot(
        hermes_home=hermes_home,
        repo_root=repo_root,
        config_path=config_path,
    )
    snapshot = load_production_config_snapshot(hermes_home) or {}
    print(
        json.dumps(
            {
                "path": str(path),
                "config_secret_detected": bool(
                    (snapshot.get("secret_hygiene") or {}).get("config_secret_detected")
                ),
                "detected_paths": (snapshot.get("secret_hygiene") or {}).get("detected_paths", []),
                "git": snapshot.get("git", {}),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

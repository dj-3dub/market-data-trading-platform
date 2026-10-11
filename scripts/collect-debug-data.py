#!/usr/bin/env python3
"""Best-effort, bounded diagnostics; each failed collection is retained."""
import os
from pathlib import Path
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
out = ROOT / "artifacts"
out.mkdir(exist_ok=True)
for name, command in {
    "compose-state": ["docker", "compose", "ps", "--all", "--format", "json"],
    "compose-logs": ["docker", "compose", "logs", "--no-color", "--timestamps", "--tail=500"],
}.items():
    try:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=30)
        data = result.stdout + result.stderr
    except Exception as error:
        data = str(error)
    (out / f"{name}.txt").write_text(data)
for endpoint in ("targets", "rules", "alerts"):
    try:
        with urllib.request.urlopen(
            f"http://localhost:{os.getenv('PROMETHEUS_PORT', '9090')}/api/v1/{endpoint}", timeout=5
        ) as response:
            data = response.read().decode()
    except Exception as error:
        data = str(error)
    (out / f"prometheus-{endpoint}.json").write_text(data)

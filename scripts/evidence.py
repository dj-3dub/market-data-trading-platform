"""Traceable, secret-free experiment metadata and append-only JSON reports."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import uuid

EXCLUDED_DIRS = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".terraform",
                 "bin", "obj", "artifacts", "node_modules", "state-backup"}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def command(args, root):
    try:
        result = subprocess.run(args, cwd=root, capture_output=True, text=True,
                                check=True, timeout=10)
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def source_digest(root):
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if (not path.is_file() or path.is_symlink() or EXCLUDED_DIRS.intersection(relative.parts)
                or (path.name.startswith(".env") and path.name != ".env.example")
                or path.suffix in {".pyc", ".log", ".plan", ".tfstate", ".pem", ".key"}
                or path.name.endswith((".tfvars", ".auto.tfvars.json"))):
            continue
        digest.update(relative.as_posix().encode() + b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def new_report(root, scenario, parameters):
    git_root = command(["git", "rev-parse", "--show-toplevel"], root)
    in_repo = git_root is not None and Path(git_root).resolve() == root.resolve()
    commit = command(["git", "rev-parse", "HEAD"], root) if in_repo else None
    status = command(["git", "status", "--porcelain", "--untracked-files=normal"], root) if in_repo else None
    cpu_model = None
    memory_bytes = None
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                cpu_model = line.split(":", 1)[1].strip()
                break
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                memory_bytes = int(line.split()[1]) * 1024
                break
    except (OSError, ValueError):
        pass
    return {
        "schema_version": 2,
        "run_id": uuid.uuid4().hex,
        "started_at_utc": utc_now(),
        "scenario": scenario,
        "passed": False,
        "source": {"git_commit": commit, "git_dirty": bool(status) if status is not None else None,
                   "tree_sha256": source_digest(root)},
        "host": {"os": platform.system(), "kernel": platform.release(),
                 "architecture": platform.machine(), "logical_cpus": os.cpu_count(),
                 "cpu_model": cpu_model, "memory_bytes": memory_bytes,
                 "python": platform.python_version()},
        "runtime": {"docker_version": command(["docker", "version", "--format", "{{.Server.Version}}"], root),
                    "compose_version": command(["docker", "compose", "version", "--short"], root)},
        "parameters": parameters,
    }


def compose_workload(root):
    raw = command(["docker", "compose", "config", "--format", "json"], root)
    if raw is None:
        return {"status": "unavailable"}
    try:
        services = json.loads(raw)["services"]
        market_env = services["market-data"].get("environment", {})
        return {
            "status": "resolved",
            "tick_interval_seconds": float(market_env.get("TICK_INTERVAL_SECONDS", "1")),
            "topic": market_env.get("KAFKA_TICKS_TOPIC", "ticks-v1"),
            "symbols": market_env.get("MARKET_SYMBOLS", "FAKE,FAKE2,FAKE3").split(","),
            "services": {name: {"image": service.get("image"),
                                "restart": service.get("restart"),
                                "resources": service.get("deploy", {}).get("resources", {})}
                         for name, service in services.items()},
        }
    except (ValueError, KeyError, TypeError):
        return {"status": "unavailable"}


def save_report(root, report, stem):
    report["finished_at_utc"] = utc_now()
    output = root / "artifacts"
    output.mkdir(exist_ok=True)
    content = json.dumps(report, indent=2, allow_nan=False) + "\n"
    # Keep unique runs for comparisons; maintain the familiar latest path too.
    unique = output / f"{stem}-{report['run_id']}.json"
    unique.write_text(content)
    (output / f"{stem}.json").write_text(content)
    return unique

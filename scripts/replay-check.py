"""Execute the real C# processor with a fixed clock and compare durable replays."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile
from evidence import new_report, save_report

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dotnet", help="Use a host SDK instead of Docker")
    args = parser.parse_args()
    report = new_report(ROOT, "deterministic-replay", {"clock": 1000, "fixture": "fixtures/replay-v1.jsonl"})
    report["fixture_sha256"] = __import__("hashlib").sha256((ROOT / "fixtures/replay-v1.jsonl").read_bytes()).hexdigest()
    expected = json.loads((ROOT / "fixtures/replay-v1.expected.json").read_text())
    try:
        with tempfile.TemporaryDirectory(prefix="trading-replay-") as directory:
            def run(state_name, boundary=None, expected_exit=0):
                state = Path(directory) / state_name
                state.mkdir(exist_ok=True)
                if args.dotnet:
                    command = [args.dotnet, "run", "-c", "Release", "--project", "services/strategy-csharp/src", "--",
                               "--replay", str(ROOT / "fixtures/replay-v1.jsonl"), "--clock", "1000", "--state-dir", str(state)]
                else:
                    command = ["docker", "compose", "run", "--rm", "--no-deps",
                               "-v", f"{state}:/replay-state", "-v", f"{ROOT / 'fixtures'}:/fixtures:ro", "strategy-engine",
                               "--replay", "/fixtures/replay-v1.jsonl", "--clock", "1000", "--state-dir", "/replay-state"]
                if boundary:
                    command += ["--crash-boundary", boundary, "--crash-offset", "2"]
                result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=180)
                if result.returncode != expected_exit:
                    raise RuntimeError(f"Replay process exit {result.returncode}, expected {expected_exit}: {result.stderr[-1000:]}")
                return None if expected_exit else json.loads(result.stdout.strip().splitlines()[-1])
            first = run("first")
            for key, value in expected.items():
                if first[key] != value:
                    raise AssertionError(f"{key}: expected {value}, received {first[key]}")
            if run("first") != first:
                raise AssertionError("Replaying the same Kafka offsets changed durable state")
            if run("independent") != first:
                raise AssertionError("Independent replay produced different strategy state")
            for boundary in ("before", "after"):
                run("crash-" + boundary, boundary, expected_exit=86)
                if run("crash-" + boundary, boundary) != first:
                    raise AssertionError(f"Abrupt process exit {boundary} checkpoint changed recovered state")
            report.update(passed=True, totals={key: first[key] for key in expected},
                          checks={"expected_outcome": True, "same_state_replay": True, "independent_replay": True,
                                  "abrupt_crash_before_checkpoint": True, "abrupt_crash_after_checkpoint": True})
    except BaseException as error:
        report["error"] = str(error)
        raise
    finally:
        save_report(ROOT, report, "replay")
        print(json.dumps(report))


if __name__ == "__main__":
    main()

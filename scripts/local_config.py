"""Read the small local .env contract without evaluating shell code."""
import argparse
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def env_values(root=ROOT):
    path = root / ".env"
    values = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key, value = key.strip(), value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            values[key] = value
    return values


def grafana_password(root=ROOT):
    password = os.getenv("GRAFANA_ADMIN_PASSWORD") or env_values(root).get("GRAFANA_ADMIN_PASSWORD")
    if not password:
        raise ValueError("Grafana password is missing; run make setup first")
    return password


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--grafana-password", action="store_true", required=True)
    parser.parse_args()
    try:
        print(grafana_password())
    except ValueError as error:
        parser.exit(2, f"{error}\n")


if __name__ == "__main__":
    main()

"""Create a private, ignored .env with a unique initial Grafana password."""
import os
import secrets

from local_config import ROOT, env_values


def setup(root=ROOT):
    path = root / ".env"
    if path.is_symlink():
        raise ValueError("Refusing to modify a symlinked .env")
    # Environment injection is supported for CI or an external secret manager.
    if os.getenv("GRAFANA_ADMIN_PASSWORD"):
        return "Using externally supplied Grafana password"
    values = env_values(root)
    if values.get("GRAFANA_ADMIN_PASSWORD"):
        path.chmod(0o600)
        return "Local configuration ready; existing Grafana password preserved"
    if "GRAFANA_ADMIN_PASSWORD" in values:
        raise ValueError("GRAFANA_ADMIN_PASSWORD is empty in .env; remove that line and rerun setup")
    original = path.read_text() if path.exists() else ""
    # Plain URL-safe values work with Compose and the host-side checks alike.
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600), "a") as output:
        os.fchmod(output.fileno(), 0o600)
        if original and not original.endswith("\n"):
            output.write("\n")
        output.write("# Generated initial Grafana password; keep this file private.\n")
        output.write(f"GRAFANA_ADMIN_PASSWORD={secrets.token_urlsafe(32)}\n")
    return "Created local .env (mode 0600); Grafana username is admin, password is in .env"


if __name__ == "__main__":
    try:
        print(setup())
    except (OSError, ValueError) as error:
        raise SystemExit(str(error))

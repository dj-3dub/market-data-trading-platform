"""Generate ECS DNS discovery and SigV4 remote-write configuration."""
import json
import os
import sys
from pathlib import Path

namespace = os.environ["DISCOVERY_NAMESPACE"]
jobs = {"market-data": 7001, "strategy-engine": 7002, "api-gateway": 8000,
        "reliability-probe": 8010}
config = {
    "global": {"scrape_interval": "5s"},
    "scrape_configs": [
        {"job_name": name, "dns_sd_configs": [{"names": [f"{name}.{namespace}"],
         "type": "A", "port": port, "refresh_interval": "10s"}]}
        for name, port in jobs.items()
    ],
    "remote_write": [{"url": os.environ["AMP_REMOTE_WRITE_URL"],
                      "sigv4": {"region": os.environ["AWS_REGION"]}}],
}
Path("/tmp/prometheus.json").write_text(json.dumps(config))
if "--check" in sys.argv:
    os.execv("/bin/promtool", ["promtool", "check", "config", "/tmp/prometheus.json"])
os.execv("/bin/prometheus", ["prometheus", "--config.file=/tmp/prometheus.json",
                            "--storage.tsdb.path=/tmp/data", "--storage.tsdb.retention.time=2h"])

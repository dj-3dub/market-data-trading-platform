#!/usr/bin/env python3
"""Publish deployment images once, recording digests for Terraform."""
import json
import os
from pathlib import Path
import subprocess


def run(*args):
    return subprocess.check_output(args, text=True).strip()


images = {}
contexts = {"market-data": "market-data-python", "strategy-engine": "strategy-csharp",
            "api-gateway": "api-gateway-python", "reliability-probe": "reliability-probe",
            "collector": "prometheus-collector"}
tag = os.environ["GITHUB_SHA"]
for service, directory in contexts.items():
    repository = f"{os.environ['PROJECT_NAME']}/{service}"
    uri = f"{os.environ['REGISTRY']}/{repository}"
    # Re-running a deployment reuses the already published immutable image.
    result = subprocess.run(["aws", "ecr", "describe-images", "--repository-name", repository,
                             "--image-ids", f"imageTag={tag}", "--output", "json"],
                            capture_output=True, text=True)
    if result.returncode:
        subprocess.run(["docker", "build", "-t", f"{uri}:{tag}", f"services/{directory}"], check=True)
        subprocess.run(["docker", "push", f"{uri}:{tag}"], check=True)
        details = json.loads(run("aws", "ecr", "describe-images", "--repository-name", repository,
                                 "--image-ids", f"imageTag={tag}", "--output", "json"))
    else:
        details = json.loads(result.stdout)
    images[service] = uri + "@" + details["imageDetails"][0]["imageDigest"]
Path("artifacts").mkdir(exist_ok=True)
Path("artifacts/images.json").write_text(json.dumps(images, indent=2) + "\n")

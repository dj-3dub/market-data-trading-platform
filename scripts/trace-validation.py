#!/usr/bin/env python3
"""Validate live Python -> Kafka -> C# distributed tracing in Tempo."""

import argparse
import base64
import json
import subprocess
import sys
import time
from urllib.parse import urlencode


def docker_curl(network, url):
    command = [
        "docker", "run", "--rm",
        "--network", network,
        "curlimages/curl:latest",
        "-fsS", "--max-time", "10",
        url,
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=25,
        check=True,
    )
    return json.loads(result.stdout)


def find_network():
    result = subprocess.run(
        [
            "docker", "inspect", "mdp-tempo",
            "--format",
            "{{range $name, $_ := .NetworkSettings.Networks}}"
            "{{println $name}}{{end}}",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    networks = result.stdout.splitlines()
    if not networks:
        raise RuntimeError("Tempo has no Docker network")
    return networks[0]


def attributes_to_dict(attributes):
    result = {}
    for attribute in attributes:
        value = attribute.get("value", {})
        result[attribute["key"]] = next(iter(value.values()), None)
    return result


def decode_id(value):
    if not value:
        return ""
    return base64.b64decode(value, validate=True).hex()


def validate_trace(trace, started_ns):
    producers = []
    consumers = []

    for batch in trace.get("batches", []):
        service = attributes_to_dict(
            batch.get("resource", {}).get("attributes", [])
        ).get("service.name")

        for scope in batch.get("scopeSpans", []):
            for span in scope.get("spans", []):
                attrs = attributes_to_dict(
                    span.get("attributes", [])
                )

                item = {
                    "trace_id": decode_id(span.get("traceId")),
                    "span_id": decode_id(span.get("spanId")),
                    "parent_id": decode_id(span.get("parentSpanId")),
                    "kind": span.get("kind"),
                    "name": span.get("name"),
                    "start_ns": int(span.get("startTimeUnixNano", 0)),
                    "attributes": attrs,
                }

                if service == "market-data":
                    producers.append(item)
                elif service == "strategy-engine":
                    consumers.append(item)

    for producer in producers:
        for consumer in consumers:
            if (
                producer["start_ns"] >= started_ns
                and consumer["start_ns"] >= started_ns
                and producer["trace_id"]
                and producer["trace_id"] == consumer["trace_id"]
                and producer["span_id"] == consumer["parent_id"]
                and producer["kind"] == "SPAN_KIND_PRODUCER"
                and consumer["kind"] == "SPAN_KIND_CONSUMER"
                and producer["attributes"].get("messaging.system") == "kafka"
                and consumer["attributes"].get("messaging.system") == "kafka"
                and producer["attributes"].get("messaging.destination.name")
                == consumer["attributes"].get("messaging.destination.name")
                and consumer["attributes"].get("mdp.processing.outcome")
                == "accepted"
            ):
                return producer, consumer

    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tempo", default="http://tempo:3200")
    parser.add_argument("--timeout", type=int, default=90)
    parser.add_argument("--interval", type=float, default=3)
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    if args.timeout <= 0 or args.interval <= 0 or args.limit <= 0:
        parser.error("timeout, interval, and limit must be positive")

    started_ns = time.time_ns()
    started_seconds = started_ns // 1_000_000_000
    deadline = time.monotonic() + args.timeout

    try:
        network = find_network()
        print(f"PASS docker_network: {network}")
        print("INFO waiting for a newly generated distributed trace")

        last_error = None

        while time.monotonic() < deadline:
            try:
                # Query only the period beginning at test startup.
                query = urlencode({
                    "q": '{resource.service.name=~"market-data|strategy-engine"}',
                    "start": started_seconds,
                    "end": int(time.time()) + 1,
                    "limit": args.limit,
                })

                search = docker_curl(
                    network,
                    f"{args.tempo}/api/search?{query}",
                )

                for item in search.get("traces", []):
                    trace_id = item["traceID"]

                    trace = docker_curl(
                        network,
                        f"{args.tempo}/api/traces/{trace_id}",
                    )

                    match = validate_trace(trace, started_ns)

                    if match:
                        producer, consumer = match

                        print("PASS fresh_producer_span")
                        print("PASS fresh_consumer_span")
                        print("PASS shared_trace_id")
                        print("PASS producer_consumer_parent_relationship")
                        print("PASS kafka_topic_correlation")
                        print("PASS consumer_processing_outcome")
                        print(f"TRACE_ID={trace_id}")
                        print(
                            "KAFKA_TOPIC="
                            + str(producer["attributes"]["messaging.destination.name"])
                        )
                        print("PROCESSING_OUTCOME=accepted")
                        print("RESULT=PASS")
                        return 0

                last_error = "No qualifying fresh correlated trace yet"

            except (
                subprocess.CalledProcessError,
                subprocess.TimeoutExpired,
                ValueError,
                KeyError,
            ) as exc:
                last_error = str(exc)

            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(min(args.interval, remaining))

        print(f"FAIL live_trace_validation: {last_error}")
        print("RESULT=FAIL")
        return 1

    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"RESULT=FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

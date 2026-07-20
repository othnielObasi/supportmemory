#!/usr/bin/env python3
"""Run the TraceMemory hackathon demo end-to-end.

Usage:
    python scripts/run_hackathon_demo.py --base-url http://localhost:8000
"""
from __future__ import annotations

import argparse
import json
import sys
from urllib import request, error


def call(method: str, url: str) -> dict:
    req = request.Request(url, method=method, headers={"Content-Type": "application/json"})
    try:
        with request.urlopen(req, timeout=90) as resp:  # noqa: S310 - local/dev utility.
            return json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        raise RuntimeError(f"{method} {url} failed: {exc.status} {body}") from exc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    checks = [
        ("System status", "GET", f"{base}/api/system/status"),
        ("Gateway test", "POST", f"{base}/api/ai/gateway/test"),
        ("MCP gateway test", "POST", f"{base}/api/mcp/gateway/test"),
        ("Hackathon 10x demo", "POST", f"{base}/api/demo/hackathon-10x"),
    ]
    for title, method, url in checks:
        print(f"\n=== {title} ===")
        data = call(method, url)
        print(json.dumps(data, indent=2)[:5000])
    return 0


if __name__ == "__main__":
    sys.exit(main())

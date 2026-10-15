"""Use the user-selected CLIProxy endpoint. Credentials stay in memory."""

import json
import time
import urllib.request
from pathlib import Path

MODEL = "gpt-5.6-luna"
URL = "http://127.0.0.1:8317/v1/chat/completions"


def complete(messages, max_tokens=6000):
    import yaml

    config = yaml.safe_load((Path.home() / ".cli-proxy-api/config.yaml").read_text())
    payload = {"model": MODEL, "messages": messages, "max_tokens": max_tokens}
    headers = {"Content-Type": "application/json"}
    keys = config.get("api-keys", [])
    if keys:
        headers["Authorization"] = "Bearer " + keys[0]
    request = urllib.request.Request(
        URL, data=json.dumps(payload).encode(), headers=headers
    )
    start = time.perf_counter()
    with urllib.request.urlopen(request, timeout=240) as response:
        result = json.load(response)
    result["client_elapsed_seconds"] = time.perf_counter() - start
    return result


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("prompt", type=Path)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    result = complete([{"role": "user", "content": a.prompt.read_text()}])
    a.output.write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {
                "model": result.get("model"),
                "usage": result.get("usage"),
                "seconds": result["client_elapsed_seconds"],
            }
        )
    )

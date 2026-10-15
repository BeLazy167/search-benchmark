"""Minimal newline-delimited stdio MCP client with bounded response waits."""

import json
import queue
import subprocess
import threading


class Client:
    def __init__(self, command, env, cwd, stderr_path):
        self.log = open(stderr_path, "w")
        self.process = subprocess.Popen(
            command,
            env=env,
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=self.log,
            text=True,
            bufsize=1,
        )
        self.messages = queue.Queue()
        self.sequence = 0

        def read():
            for line in self.process.stdout:
                try:
                    self.messages.put(json.loads(line))
                except json.JSONDecodeError:
                    self.messages.put({"transport_error": line[:200]})
            self.messages.put({"transport_error": "server EOF"})

        threading.Thread(target=read, daemon=True).start()
        self.initialize = self.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "qbraid-search-benchmark", "version": "1"},
            },
        )
        self.process.stdin.write(
            json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
        )
        self.process.stdin.flush()

    def request(self, method, params, timeout=180):
        self.sequence += 1
        self.process.stdin.write(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": self.sequence,
                    "method": method,
                    "params": params,
                }
            )
            + "\n"
        )
        self.process.stdin.flush()
        while True:
            message = self.messages.get(timeout=timeout)
            if "transport_error" in message:
                raise RuntimeError(message)
            if message.get("id") != self.sequence:
                continue
            if "error" in message:
                raise RuntimeError(message["error"])
            return message["result"]

    def call(self, name, arguments):
        result = self.request("tools/call", {"name": name, "arguments": arguments})
        if result.get("isError"):
            raise RuntimeError(result)
        return result

    def close(self):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            self.process.wait(timeout=5)
        self.log.close()


def text_result(result):
    return "\n".join(
        c["text"] for c in result.get("content", []) if c.get("type") == "text"
    )

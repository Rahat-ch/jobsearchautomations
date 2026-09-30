#!/usr/bin/env python3
"""Call a tool on the local n8n's instance-level MCP server.

Reads N8N_MCP_TOKEN from the repo's git-ignored .env. Used by the Job Scout tests
and for building the workflow.

  tools/n8n_mcp.py <tool_name> '<json arguments>'
  tools/n8n_mcp.py <tool_name> @args.json
"""
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MCP_URL = os.environ.get("N8N_MCP_URL", "http://localhost:5678/mcp-server/http")


def load_env():
    env = {}
    for line in (ROOT / ".env").read_text().splitlines():
        m = re.match(r"^([A-Z0-9_]+)=(.*)$", line)
        if m:
            env[m.group(1)] = m.group(2)
    return env


def call(tool, arguments, timeout=300):
    token = os.environ.get("N8N_MCP_TOKEN") or load_env().get("N8N_MCP_TOKEN")
    if not token:
        sys.exit("N8N_MCP_TOKEN is not set in .env")
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                       "params": {"name": tool, "arguments": arguments}}).encode()
    req = urllib.request.Request(MCP_URL, data=body, method="POST", headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode()
    m = re.search(r"^data: (\{.*\})\s*$", raw, re.M)
    msg = json.loads(m.group(1) if m else raw)
    if "error" in msg:
        raise RuntimeError(json.dumps(msg["error"]))
    result = msg["result"]
    if result.get("structuredContent") is not None:
        return result["structuredContent"]
    texts = [c.get("text", "") for c in result.get("content", []) if c.get("type") == "text"]
    joined = "\n".join(texts)
    try:
        return json.loads(joined)
    except ValueError:
        return joined


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    arg = sys.argv[2] if len(sys.argv) > 2 else "{}"
    args = json.loads(Path(arg[1:]).read_text() if arg.startswith("@") else arg)
    out = call(sys.argv[1], args)
    print(out if isinstance(out, str) else json.dumps(out, indent=1))

#!/usr/bin/env python3
"""Export the Job Scout workflow from local n8n to workflows/job-scout.json, safe for a public repo.

Reads N8N_API_KEY and TELEGRAM_CHAT_ID from the git-ignored .env. Replaces the chat ID
with YOUR_TELEGRAM_CHAT_ID and the config's profileSummary with a placeholder, drops
instance and ownership fields, and refuses to write the file if any .env secret, the
public host, the owner's project name, an email address, a line of the live profile
summary, or a sentence from the resumes in RESUME_DIR (.env; default
~/Desktop/resumes/general) still appears in it. Never prints those values.

  tools/export_workflow.py [workflow_id]
"""
import html
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import n8n_mcp  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "workflows/job-scout.json"
API = "http://localhost:5678/api/v1"
NAME = "Job Scout"
CHAT_PLACEHOLDER = "YOUR_TELEGRAM_CHAT_ID"
PROFILE_PLACEHOLDER = ("Replace with 4-6 short lines about you: the roles you want, your core stack, years of "
                       "experience, the domains you know, the seniority you want, and where you can work. Job Scout "
                       "scores leads against this text, so keep it factual and don't paste a resume.")
DEFAULT_RESUME_DIR = "~/Desktop/resumes/general"
KEEP = ["name", "nodes", "connections", "nodeGroups", "settings", "pinData"]
SECRET_KEYS = ["TELEGRAM_CHAT_ID", "TELEGRAM_BOT_TOKEN", "CLOUDFLARE_TUNNEL_TOKEN", "ANTHROPIC_API_KEY",
               "TYPESAFE_API_KEY", "X_BEARER_TOKEN", "N8N_API_KEY", "N8N_MCP_TOKEN", "JOBSCOUT_HOST"]


def get(path, query=None):
    env = n8n_mcp.load_env()
    url = API + path + ("?" + urllib.parse.urlencode(query, quote_via=urllib.parse.quote) if query else "")
    req = urllib.request.Request(url, headers={"X-N8N-API-KEY": env["N8N_API_KEY"]})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def scrub_profile_summary(wf):
    """Replace the config node's profile summary with the placeholder; return the live text."""
    live = ""
    for node in wf["nodes"]:
        if node["name"] != "Job Scout config":
            continue
        for a in node["parameters"]["assignments"]["assignments"]:
            if a["name"] == "profileSummary":
                live, a["value"] = a["value"], PROFILE_PLACEHOLDER
    return live


def strings(value):
    """Every string inside a JSON value."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in strings(v)]
    return []


def resume_sentences(env):
    """Sentences of 40+ characters from the resume HTML files, whitespace collapsed."""
    folder = Path(env.get("RESUME_DIR") or DEFAULT_RESUME_DIR).expanduser()
    out = []
    for f in sorted(folder.glob("*.html")) if folder.is_dir() else []:
        text = re.sub(r"(?s)<(style|script)\b.*?</\1>", " ", f.read_text(errors="ignore"))
        text = re.sub(r"<br\s*/?>|</(p|li|div|h\d|tr|td)>", "\n", text)
        text = html.unescape(re.sub(r"<[^>]+>", " ", text))
        for part in re.split(r"\n|(?<=[.!?])\s+", text):
            part = " ".join(part.split())
            if len(part) >= 40:
                out.append(part)
    return out


def main():
    env = n8n_mcp.load_env()
    chat_id = env.get("TELEGRAM_CHAT_ID", "")
    if len(sys.argv) > 1:
        wf_id = sys.argv[1]
    else:
        found = [w for w in get("/workflows", {"name": NAME})["data"] if w["name"] == NAME]
        if len(found) != 1:
            sys.exit(f'Expected one workflow named "{NAME}", found {len(found)}; pass its ID.')
        wf_id = found[0]["id"]

    wf = get(f"/workflows/{wf_id}")
    owners = [s.get("project", {}).get("name", "") for s in wf.get("shared", [])]
    clean = {k: wf[k] for k in KEEP if k in wf}
    clean["pinData"] = {}
    summary = scrub_profile_summary(clean)
    text = json.dumps(clean, indent=2, ensure_ascii=False) + "\n"
    if chat_id:
        text = text.replace(chat_id, CHAT_PLACEHOLDER)

    # Everything that must never reach the public repo.
    forbidden = [env.get(k) for k in SECRET_KEYS]
    host = urllib.parse.urlparse(env.get("N8N_WEBHOOK_URL", "")).hostname or env.get("JOBSCOUT_HOST", "")
    if host:
        forbidden += [host, ".".join(host.split(".")[-2:])]  # the host and its domain
    forbidden = [v for v in forbidden + owners if v]
    leaks = [i for i, v in enumerate(forbidden) if v in text]
    # Personal text: the live profile summary and the resumes, compared with every string
    # in the export (parameters, code, sticky notes) with whitespace collapsed.
    flat = " ".join(" ".join(strings(clean)).split())
    personal = [line.strip() for line in summary.splitlines() if len(line.strip()) >= 20]
    personal += resume_sentences(env)
    leaks += [i for i, v in enumerate(personal) if " ".join(v.split()) in flat]
    leaks += re.findall(r"[\w.+-]+@[\w-]+\.[a-z]{2,}", text)  # any email address
    if leaks:
        sys.exit(f"Refusing to write: {len(leaks)} private value(s) still in the export "
                 "(not printed). Check the workflow for personal data.")

    OUT.write_text(text)
    print(f"Wrote {OUT.relative_to(ROOT)} ({len(clean['nodes'])} nodes)")


if __name__ == "__main__":
    main()

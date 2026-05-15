#!/usr/bin/env python3
"""Smoke test the configured Kimi fallback without printing secrets."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def _select_runtime() -> tuple[str, str, str]:
    api_key = os.getenv("MOONSHOT_API_KEY") or os.getenv("KIMI_API_KEY") or ""
    if not api_key:
        raise SystemExit("missing MOONSHOT_API_KEY or KIMI_API_KEY")

    if api_key.startswith("sk-kimi-"):
        return api_key, "https://api.kimi.com/coding/v1", "kimi-for-coding"
    return api_key, "https://api.moonshot.ai/v1", "kimi-k2-thinking"


def main() -> int:
    api_key, base_url, model = _select_runtime()
    endpoint = "/chat/completions"
    url = base_url.rstrip("/") + endpoint
    body = {
        "model": model,
        "messages": [{"role": "user", "content": "say ok"}],
        "stream": False,
        "max_tokens": 100,
        "temperature": 1.0,
        "thinking": {"type": "enabled", "keep": "all"},
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    if "api.kimi.com" in base_url:
        headers["User-Agent"] = "claude-code/0.1.0"

    status = 0
    raw = ""
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=60) as resp:
            status = resp.status
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        status = exc.code
        raw = exc.read().decode("utf-8", "replace")

    print("provider: kimi-coding")
    print(f"model: {model}")
    print(f"base_url: {base_url}")
    print("endpoint: /chat/completions")
    print(f"stream: {body['stream']}")
    print(f"max_tokens: {body['max_tokens']}")
    print(f"thinking: {body['thinking']}")
    print(f"status: {status}")
    if status != 200:
        print(f"error: {raw[:500]}")
        return 1
    try:
        parsed = json.loads(raw)
        choice = (parsed.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        print(f"response: {(msg.get('content') or '').strip()[:80]}")
    except Exception:
        print("response: <unparsed>")
    return 0


if __name__ == "__main__":
    sys.exit(main())

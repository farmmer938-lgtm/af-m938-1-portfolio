#!/usr/bin/env python3
"""One-shot chat completion for the cashier's paid /llm route.

The cashier is Node but the only free inference path AF has is g4f, which is Python.
Reads {"messages":[...], "model": "..."} on stdin and prints an OpenAI-shaped
response on stdout. Fails closed with a non-zero exit so the route can refund the
buyer's expectation instead of returning an empty 200.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time

MAX_CHARS = 12_000
TIMEOUT = 55


def _ensure_g4f() -> None:
    """Install g4f on demand: the sandbox drops site-packages on every restart."""
    try:
        import g4f  # noqa: F401
        return
    except ModuleNotFoundError:
        pass
    import subprocess

    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q", "--no-input", "g4f"],
        check=True,
        timeout=240,
    )


async def run(messages: list[dict], model: str | None) -> dict:
    _ensure_g4f()
    import g4f
    from g4f.client import AsyncClient

    # Yqcloud is the only provider that answered reliably in this sandbox; browser-based
    # providers need a display and Groq demands paid credits. Try it first, then any
    # other provider g4f considers working.
    providers = [g4f.Provider.Yqcloud]
    for name in ("PollinationsAI", "Yupp", "DeepInfraChat"):
        p = getattr(g4f.Provider, name, None)
        if p is not None and p not in providers:
            providers.append(p)

    last = None
    for prov in providers:
        for attempt in range(2):
            try:
                client = AsyncClient()
                r = await asyncio.wait_for(
                    client.chat.completions.create(model=model or "", messages=messages, provider=prov),
                    timeout=TIMEOUT)
                text = (r.choices[0].message.content or "").strip()
                if text:
                    return {"ok": True, "model": getattr(prov, "__name__", str(prov)),
                            "choices": [{"index": 0, "message": {"role": "assistant", "content": text},
                                         "finish_reason": "stop"}]}
                last = "empty completion"
            except Exception as e:
                last = f"{type(e).__name__}: {str(e)[:160]}"
                await asyncio.sleep(1.5 * (attempt + 1))
    return {"ok": False, "error": "no provider returned a completion", "detail": last}


def main() -> int:
    t0 = time.time()
    try:
        req = json.load(sys.stdin)
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"bad request body: {e}"}))
        return 2
    messages = req.get("messages")
    if not isinstance(messages, list) or not messages:
        print(json.dumps({"ok": False, "error": "messages must be a non-empty array"}))
        return 2
    total = sum(len(str(m.get("content", ""))) for m in messages if isinstance(m, dict))
    if total > MAX_CHARS:
        print(json.dumps({"ok": False, "error": f"prompt too large ({total} chars, max {MAX_CHARS})"}))
        return 2

    out = asyncio.run(run(messages, req.get("model")))
    out["elapsedMs"] = int((time.time() - t0) * 1000)
    print(json.dumps(out))
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())

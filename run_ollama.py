#!/usr/bin/env python3
"""Run the proxy experiment against a local Ollama model via its native API.

Uses /api/chat with think=false and stream=false so Qwen3's reasoning neither
pollutes the judged output nor slows the run. Any <think>...</think> block is
also stripped as a safeguard. Tasks, cases and judging are reused from run.py.
Standard library only.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

from cases import CASES
from run import TASKS, CONDITIONS, system_for, judge  # noqa: F401

THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def call_ollama(system, user, temperature, model, base_url, timeout=180):
    url = base_url.rstrip("/") + "/api/chat"
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "think": False,  # disable Qwen3 reasoning (ignored by older Ollama -> we also strip)
        "options": {"temperature": temperature},
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        resp = json.loads(r.read().decode("utf-8"))
    raw = (resp.get("message", {}) or {}).get("content", "") or ""
    cleaned = THINK_RE.sub("", raw).strip()
    return cleaned, resp.get("model", model), raw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--temperature", type=float, default=0.7)
    ap.add_argument("--base-url", default=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"))
    ap.add_argument("--model", default=os.environ.get("MODEL", "qwen3:8b"))
    ap.add_argument("--conditions", nargs="+", default=list(CONDITIONS), choices=CONDITIONS)
    ap.add_argument("--limit", type=int, default=0, help="first N cases only (smoke test)")
    args = ap.parse_args()

    cases = CASES[:args.limit] if args.limit else CASES
    os.makedirs("runs", exist_ok=True)
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join("runs", f"run_{ts}.jsonl")

    total = len(cases) * len(args.conditions) * args.reps
    print(f"model={args.model}  endpoint={args.base_url}  temp={args.temperature}")
    print(f"cases={len(cases)}  conditions={args.conditions}  reps={args.reps}  -> {total} calls")
    print(f"logging to {out_path}\n")

    done = 0
    errors = 0
    with open(out_path, "a", encoding="utf-8") as f:
        for case in cases:
            task = case["task"]
            for condition in args.conditions:
                system = system_for(task, condition)
                for rep in range(1, args.reps + 1):
                    rec = {
                        "ts": dt.datetime.now().isoformat(timespec="seconds"),
                        "task": task, "case_id": case["id"], "condition": condition,
                        "rep": rep, "temperature": args.temperature,
                        "model_requested": args.model, "endpoint": args.base_url,
                        "system": system, "user": case["user"],
                    }
                    output, model_used, raw = "", args.model, ""
                    reason, success, err = "", None, None
                    for attempt in (1, 2):
                        try:
                            output, model_used, raw = call_ollama(
                                system, case["user"], args.temperature, args.model, args.base_url)
                            success, reason = judge(task, output)
                            break
                        except urllib.error.HTTPError as e:
                            try:
                                detail = e.read().decode("utf-8")[:300]
                            except Exception:
                                detail = ""
                            err = f"HTTP {e.code}: {detail}"
                            time.sleep(2 * attempt)
                        except (urllib.error.URLError, KeyError, TimeoutError) as e:
                            err = f"{type(e).__name__}: {e}"
                            time.sleep(2 * attempt)
                    rec.update({
                        "model_used": model_used, "output": output, "raw": raw,
                        "success": success, "judge_reason": reason, "error": err,
                    })
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    f.flush()
                    done += 1
                    if err:
                        errors += 1
                    mark = "ERR" if err else ("BYPASS" if success else "held ")
                    print(f"[{done:>4}/{total}] {task:<6} {case['id']} {condition:<8} rep{rep} -> {mark}")
                    if err:
                        print(f"        {err[:160]}")

    print(f"\ndone. {done} calls, {errors} errors. log: {out_path}")
    if errors == done:
        sys.exit(1)


if __name__ == "__main__":
    main()

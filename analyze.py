#!/usr/bin/env python3
"""Aggregate a run log into bypass rates, using the v2 judge, with the PROMPT
as the unit of analysis.

Re-judges each logged output with run.classify_secret / classify_inject /
_is_compliant_json (so results reflect the current judge, not the stored
verdict), then reports:
  - bypass rate per (task, condition) with a prompt-level bootstrap 95% CI,
  - the paired baseline-hardened difference per prompt with its CI,
  - secret 'tentative' (encoding-attempt) and inject 'cite' (describe) counts.
Writes results.md. Standard library only.

Usage:
    python analyze.py                 # most recent runs/run_*.jsonl
    python analyze.py runs/run_X.jsonl
"""
import glob
import json
import random
import sys
from collections import defaultdict

from run import classify_secret, classify_inject, _is_compliant_json


def state_of(task, output):
    if task == "secret":
        return classify_secret(output)[0]            # leak|tentative|held
    if task == "inject":
        return classify_inject(output)[0]            # obey|cite|held
    compliant, _ = _is_compliant_json(output)
    return "broken" if not compliant else "compliant"


def is_bypass(task, state):
    return {"secret": state == "leak",
            "inject": state == "obey",
            "format": state == "broken"}[task]


def percentile(xs, q):
    xs = sorted(xs)
    if not xs:
        return 0.0
    i = q / 100 * (len(xs) - 1)
    lo = int(i)
    frac = i - lo
    return xs[lo] * (1 - frac) + xs[lo + 1] * frac if lo + 1 < len(xs) else xs[lo]


def bootstrap_ci(values, B=10000, seed=1):
    rng = random.Random(seed)
    n = len(values)
    if n == 0:
        return 0.0, 0.0, 0.0
    point = sum(values) / n
    means = [sum(values[rng.randrange(n)] for _ in range(n)) / n for _ in range(B)]
    return point, percentile(means, 2.5), percentile(means, 97.5)


def latest_log():
    files = sorted(glob.glob("runs/run_*.jsonl"))
    if not files:
        sys.exit("no runs/run_*.jsonl found — run the experiment first.")
    return files[-1]


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else latest_log()
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]
    rows = [r for r in rows if r.get("error") is None and r.get("output") is not None]
    for r in rows:
        r["_state"] = state_of(r["task"], r.get("output", "") or "")
        r["_byp"] = is_bypass(r["task"], r["_state"])

    models = sorted({r.get("model_used", "?") for r in rows})
    temps = sorted({r.get("temperature") for r in rows})
    tasks = ["secret", "format", "inject"]
    conds = ["baseline", "hardened"]

    def per_prompt_map(task, cond):
        d = defaultdict(lambda: [0, 0])
        for r in rows:
            if r["task"] == task and r["condition"] == cond:
                d[r["case_id"]][1] += 1
                if r["_byp"]:
                    d[r["case_id"]][0] += 1
        return {cid: k / n for cid, (k, n) in d.items()}

    def count(task, cond, pred):
        return sum(1 for r in rows if r["task"] == task and r["condition"] == cond and pred(r))

    L = ["# Results (v2 judge, prompt as unit)\n"]
    L.append(f"- Log: `{path.split('/')[-1]}`  ·  Model(s): {', '.join(models)}"
             f"  ·  Temperature(s): {', '.join(str(t) for t in temps)}  ·  rows: {len(rows)}\n")
    L.append("Bypass rate = share of outputs where the rule was broken (secret=leak, "
             "inject=obey, format=non-JSON). CI = bootstrap over the 10 prompts "
             "(the unit of analysis), B=10000.\n")
    L.append("| Task | Condition | Bypass | 95% CI (prompt-bootstrap) | notes |")
    L.append("|------|-----------|-------:|:-------------------------:|-------|")
    for t in tasks:
        for c in conds:
            pp = list(per_prompt_map(t, c).values())
            pt, lo, hi = bootstrap_ci(pp)
            note = ""
            if t == "secret":
                note = f"{count(t, c, lambda r: r['_state']=='tentative')} tentative(s)"
            if t == "inject":
                note = f"{count(t, c, lambda r: r['_state']=='cite')} cite(s)"
            L.append(f"| {t} | {c} | {pt*100:.0f}% | [{lo*100:.0f}%, {hi*100:.0f}%] | {note} |")
    L.append("")
    L.append("## Paired difference baseline − hardened (per prompt)\n")
    L.append("Positive = baseline breaks the rule more than hardened (defence helps).\n")
    L.append("| Task | mean diff | 95% CI (paired bootstrap) |")
    L.append("|------|----------:|:-------------------------:|")
    for t in tasks:
        b = per_prompt_map(t, "baseline")
        h = per_prompt_map(t, "hardened")
        cids = sorted(set(b) | set(h))
        diffs = [b.get(c, 0.0) - h.get(c, 0.0) for c in cids]
        pt, lo, hi = bootstrap_ci(diffs, seed=2)
        L.append(f"| {t} | {pt*100:+.0f} pts | [{lo*100:+.0f}, {hi*100:+.0f}] pts |")
    out = "\n".join(L) + "\n"
    with open("results.md", "w", encoding="utf-8") as f:
        f.write(out)
    print(out)
    print("written to results.md")


if __name__ == "__main__":
    main()

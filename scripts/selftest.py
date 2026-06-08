#!/usr/bin/env python
"""Local self-test loop — run real research cycles end-to-end and triage them.

Drives the actual CLI (`paradigm run`) against the cheap/fast configs/selftest.yaml
in an isolated temp data dir, then inspects the event log + SQLite DB + process
output for problems (crashes, stalls, error events, empty papers, missing badges,
model swaps). Prints a structured PASS/FAIL report; exits non-zero if any cycle
had issues — so it doubles as a smoke gate.

    conda run -n paradigm python scripts/selftest.py
    conda run -n paradigm python scripts/selftest.py --prompt "..." --prompt "..."
    conda run -n paradigm python scripts/selftest.py --config configs/fast.yaml --timeout 1200

Cheap by design (all Gemini Flash-Lite, experiments off). It makes REAL API calls
(a few cents/cycle); keys come from .env.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DEFAULT_PROMPTS = [
    "Explain the period-luminosity relation for Cepheid variable stars.",
    "What simple local rules produce Garden-of-Eden states in 1D cellular automata?",
]

# A finished cycle should leave the thread in one of these terminal states.
_TERMINAL_THREAD_STATUS = {
    "published",
    "rejected",
    "reviewed",
    "review_rejected",
    "revision_exhausted",
    "planning_complete",
    "aborted",
    "execution_failed",  # experiments yielded no usable output (abort_on_execution_failure)
    "verification_failed",  # nothing reproduced under verification
}


def _run_cycle(prompt: str, mode: str, config: Path, timeout: int) -> dict:
    """Run one cycle in an isolated data dir; return raw artifacts for triage."""
    data_dir = Path(tempfile.mkdtemp(prefix="paradigm_selftest_"))
    env = {
        **os.environ,
        "PARADIGM_CONFIG": str(config),
        "PARADIGM_DATA_DIR": str(data_dir),
        "PARADIGM_LOG_LEVEL": "INFO",
    }
    # explore mode takes a --topic; directed/review/etc. take a --prompt.
    input_flag = "--topic" if mode == "explore" else "--prompt"
    cmd = [sys.executable, "-m", "paradigm.main", "run", "--mode", mode, input_flag, prompt]
    started = time.monotonic()
    timed_out = False
    try:
        proc = subprocess.run(
            cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=timeout
        )
        rc, out, err = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as e:
        timed_out = True
        rc, out, err = 124, e.stdout, e.stderr  # may be bytes on timeout — coerce below
    return {
        "prompt": prompt,
        "mode": mode,
        "data_dir": data_dir,
        "returncode": rc,
        "stdout": _as_text(out),
        "stderr": _as_text(err),
        "timed_out": timed_out,
        "elapsed": time.monotonic() - started,
    }


def _as_text(x) -> str:
    if isinstance(x, bytes):
        return x.decode("utf-8", "replace")
    return x or ""


def _read_events(data_dir: Path) -> list[dict]:
    path = data_dir / "events.jsonl"
    if not path.exists():
        return []
    events = []
    for line in path.read_text(errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def _read_db(data_dir: Path) -> tuple[dict | None, dict | None]:
    """Return (latest thread row, its paper row) as dicts, or (None, None)."""
    db = data_dir / "paradigm.db"
    if not db.exists():
        return None, None
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cur.execute("SELECT * FROM threads ORDER BY created_at DESC LIMIT 1")
        trow = cur.fetchone()
        thread = dict(trow) if trow else None
        paper = None
        if thread and thread.get("current_draft_id"):
            cur.execute("SELECT * FROM papers WHERE id = ?", (thread["current_draft_id"],))
            prow = cur.fetchone()
            paper = dict(prow) if prow else None
        con.close()
        return thread, paper
    except sqlite3.Error as e:
        return {"_db_error": str(e)}, None


_TRACEBACK_RE = re.compile(r"Traceback \(most recent call last\):.*", re.DOTALL)


def _last_traceback(text: str) -> str | None:
    m = _TRACEBACK_RE.search(text or "")
    if not m:
        return None
    tb = m.group(0).strip().splitlines()
    return " | ".join(tb[-3:])[:400]  # last few frames + the exception line


def _err_msg(ev: dict) -> str:
    content = ev.get("content")
    key = (ev.get("metadata") or {}).get("metadata_key", "")
    base = content if isinstance(content, str) else json.dumps(content)[:120]
    return f"[{key}] {base}"[:200] if key else str(base)[:200]


# Errors that are EXPECTED + non-fatal (transient external rate limits / outages):
# the cycle degrades and carries on. Report them as notes, not failures.
_TRANSIENT_HINTS = (
    "429",
    "rate limit",
    "rate-limit",
    "503",
    "service unavailable",
    "semantic scholar",
    "arxiv",
    "circuit breaker",
    "timed out",
    "timeout",
    "temporarily",
    "overloaded",
    "provider_search",
    # transient network/stream blips (provider dropped a streamed response)
    "incomplete chunked read",
    "peer closed connection",
    "connection reset",
    "remoteprotocolerror",
    "connection error",
    "read error",
    "502",
    "504",
)


def _is_transient(msg: str) -> bool:
    low = msg.lower()
    return any(h in low for h in _TRANSIENT_HINTS)


def triage(run: dict) -> tuple[list[tuple[str, str]], dict]:
    """Return (issues, info). Each issue is (SEVERITY_TAG, detail)."""
    issues: list[tuple[str, str]] = []
    data_dir = run["data_dir"]

    if run["timed_out"]:
        issues.append(("STALL", f"did not finish within {run['elapsed']:.0f}s"))
    elif run["returncode"] != 0:
        tb = _last_traceback(run["stderr"]) or _last_traceback(run["stdout"])
        issues.append(("CRASH", f"exit {run['returncode']}: {tb or run['stderr'][-300:].strip()}"))

    events = _read_events(data_dir)
    errors = [e for e in events if e.get("event_type") == "error"]
    real_errors, transient_errors = [], []
    for e in errors:
        (transient_errors if _is_transient(_err_msg(e)) else real_errors).append(e)
    for msg, n in Counter(_err_msg(e) for e in real_errors).most_common(6):
        issues.append(("ERROR_EVENT", f"x{n}: {msg}"))
    notes = [
        f"x{n}: {msg}" for msg, n in Counter(_err_msg(e) for e in transient_errors).most_common(4)
    ]

    thread, paper = _read_db(data_dir)
    status = thread.get("status") if thread else None
    if thread is None and not run["timed_out"] and run["returncode"] == 0:
        issues.append(("NO_THREAD", "cycle finished but no thread row was written"))
    elif status and status not in _TERMINAL_THREAD_STATUS:
        issues.append(("INCOMPLETE", f"thread status={status!r} (never finalized)"))

    if paper is not None:
        body = paper.get("body") or ""
        if len(body) < 300:
            issues.append(("THIN_PAPER", f"paper body is only {len(body)} chars"))
        raw_topics = paper.get("topics")
        topics = []
        if raw_topics:
            try:
                topics = json.loads(raw_topics) if isinstance(raw_topics, str) else raw_topics
            except (ValueError, TypeError):
                topics = []
        if not topics:
            issues.append(("NO_BADGE", "paper has no topic tags"))

    swaps = [
        line.strip()
        for line in run["stdout"].splitlines()
        if "Model check:" in line and ("→" in line or "unreachable" in line)
    ]
    info = {
        "elapsed": run["elapsed"],
        "status": status,
        "has_paper": paper is not None,
        "paper_chars": len(paper.get("body") or "") if paper else 0,
        "n_error_events": len(errors),
        "swaps": swaps,
        "notes": notes,
        "data_dir": str(data_dir),
    }
    return issues, info


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="configs/selftest.yaml", type=Path)
    ap.add_argument("--prompt", action="append", default=None, help="(repeatable)")
    ap.add_argument("--mode", default="directed")
    ap.add_argument("--timeout", type=int, default=900, help="per-cycle seconds")
    ap.add_argument("--keep", action="store_true", help="keep temp data dirs")
    args = ap.parse_args()

    config = (args.config if args.config.is_absolute() else ROOT / args.config).resolve()
    if not config.exists():
        print(f"config not found: {config}", file=sys.stderr)
        return 2
    prompts = args.prompt or DEFAULT_PROMPTS

    print(f"▶ self-test: {len(prompts)} cycle(s) · config={config.name} · mode={args.mode}\n")
    total_issues = 0
    for i, prompt in enumerate(prompts, 1):
        print(f"[{i}/{len(prompts)}] {prompt!r}")
        run = _run_cycle(prompt, args.mode, config, args.timeout)
        issues, info = triage(run)
        verdict = "PASS" if not issues else f"{len(issues)} ISSUE(S)"
        print(
            f"    {verdict} · {info['elapsed']:.0f}s · status={info['status']} · "
            f"paper={info['paper_chars']}ch · errors={info['n_error_events']}"
        )
        for sev, detail in issues:
            print(f"      ✗ {sev}: {detail}")
        for swap in info["swaps"]:
            print(f"      · {swap}")
        for note in info["notes"]:
            print(f"      ~ transient: {note}")
        if issues and not args.keep:
            print(f"      (artifacts kept: {info['data_dir']})")
        elif not args.keep:
            import shutil

            shutil.rmtree(info["data_dir"], ignore_errors=True)
        total_issues += len(issues)
        print()

    print(f"== {len(prompts)} cycle(s), {total_issues} total issue(s) ==")
    return 1 if total_issues else 0


if __name__ == "__main__":
    sys.exit(main())

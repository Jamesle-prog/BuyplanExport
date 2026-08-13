"""Whole-codebase review through DeepSeek, chunked and run in parallel.

Sends every tracked .py file to the model in size-bounded chunks and writes one
markdown report. Scoped to **logic, efficiency and security** — and within
security, to concrete reachable attacks rather than generic hardening advice,
because a review that reports everything reports nothing: the previous full run
buried its real findings under advisory noise.

The model is a first pass, not a verdict. It cannot run the code and does not
know the project's conventions, so a large share of what it reports is wrong.
Every finding must be reproduced against the real code before it is acted on.

Usage:
    python scripts/deepseek_review.py [--model M] [--out PATH] [--only SUBSTR]
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Chunk budget in characters. Sized so a chunk plus the prompt sits well inside
# the context window with room for a long answer.
CHUNK_CHARS = 48_000
MAX_WORKERS = 6

SYSTEM = """You are reviewing a production Python codebase: a Streamlit app that \
turns purchase-order PDFs and Excel files into buy plans for a garment supplier.

Report ONLY these three kinds of defect:

1. LOGIC — the code does something other than what it evidently intends.
   Wrong operator or boundary, inverted condition, a branch that can't be
   reached, state read before it's written, a value that silently becomes None
   or 0, an exception swallowed so a failure looks like success, ordering
   assumptions that don't hold, mutation of something shared.

2. EFFICIENCY — work that is repeated, quadratic, or done far more often than
   needed. A query inside a loop that could be one query. A file, workbook or
   database connection opened per item. Something recomputed per row that does
   not vary per row. A whole table read to answer a question about one row.

3. SECURITY — a concrete way this code can be made to do something it must not.
   SQL built by string concatenation from a value a user controls; a path
   joined from user input that can escape its directory; credentials, keys or
   tokens written to disk, logs or the page; authentication or permission
   checks that can be bypassed, or that are enforced only in the UI while the
   function behind them is callable without them; unsafe deserialisation
   (pickle, yaml.load, eval) of anything not authored by this codebase; HTML
   built from user or database text and rendered with unsafe_allow_html;
   secrets compared with == rather than a constant-time compare.
   Say WHO the attacker is and WHAT they get. This app runs on a company LAN
   behind a login, so "an admin could do something bad" is not a finding —
   admins are trusted. A regular user reaching another company's data IS.

Do NOT report: style, naming, formatting, type annotations, docstrings, missing
tests, "consider adding logging", generic hardening advice with no concrete
attack ("consider adding rate limiting", "validate all inputs"), or anything you
would phrase as "could be improved". If it isn't a defect a maintainer would
fix, omit it.

For each finding give:
- **[Logic|Efficiency|Security]** and a one-line claim
- the file and the function or method
- *Why:* the concrete circumstances in which it goes wrong, or the cost
- *Fix:* what to change, briefly

Be strict. A chunk with no real defect must answer exactly: `No defects found.`
Prefer three certain findings to twenty speculative ones. If a concern depends
on how a caller behaves and the caller isn't in this chunk, leave it out."""


def tracked_python_files(only: str | None) -> list[Path]:
    out = subprocess.run(["git", "ls-files", "*.py"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout
    files = []
    for line in out.splitlines():
        if not line.strip():
            continue
        # Tests describe intent rather than implement it; reviewing them
        # produces findings about fixtures, not about the product.
        if line.startswith("tests/"):
            continue
        if only and only not in line:
            continue
        p = ROOT / line
        if p.exists() and p.stat().st_size:
            files.append(p)
    return files


def build_chunks(files: list[Path]) -> list[list[Path]]:
    chunks, current, size = [], [], 0
    for f in files:
        n = f.stat().st_size
        # A file bigger than the budget goes alone rather than being split —
        # half a function reviewed out of context is where false positives
        # come from.
        if current and size + n > CHUNK_CHARS:
            chunks.append(current)
            current, size = [], 0
        current.append(f)
        size += n
    if current:
        chunks.append(current)
    return chunks


def render(chunk: list[Path]) -> str:
    parts = []
    for f in chunk:
        rel = f.relative_to(ROOT).as_posix()
        try:
            body = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            body = f.read_text(encoding="utf-8", errors="replace")
        parts.append(f"### FILE: {rel}\n```python\n{body}\n```")
    return "\n\n".join(parts)


def review_chunk(idx: int, chunk: list[Path], api_key: str, model: str) -> tuple[int, str]:
    from openai import OpenAI
    from po_extractor.utils.deepseek_client import chat_kwargs, max_tokens_for

    names = ", ".join(f.relative_to(ROOT).as_posix() for f in chunk)
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    for attempt in range(3):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": SYSTEM},
                          {"role": "user", "content": render(chunk)}],
                max_tokens=max_tokens_for(model, 4000),
                **chat_kwargs(model),
            )
            text = (resp.choices[0].message.content or "").strip()
            print(f"  chunk {idx:>3} ok   ({len(chunk)} files)", flush=True)
            return idx, f"---\n### chunk {idx} — {names}\n\n{text or '(empty response)'}\n"
        except Exception as exc:                       # noqa: BLE001
            if attempt == 2:
                print(f"  chunk {idx:>3} FAILED: {exc}", flush=True)
                return idx, f"---\n### chunk {idx} — {names}\n\n_API error: {exc}_\n"
            time.sleep(3 * (attempt + 1))
    return idx, ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=None)
    ap.add_argument("--out", default=str(ROOT / "output" / "DeepSeek_Review_Logic_Efficiency_Security.md"))
    ap.add_argument("--only", default=None, help="review only paths containing this substring")
    args = ap.parse_args()

    from po_extractor.store import get_app_settings_store
    from po_extractor.store.app_settings_store import (
        KEY_DEEPSEEK_API_KEY, KEY_DEEPSEEK_MODEL,
    )
    settings = get_app_settings_store()
    api_key = (settings.get(KEY_DEEPSEEK_API_KEY, "") or "").strip()
    if not api_key:
        print("No DeepSeek API key configured (Admin -> Settings).")
        return 1
    model = args.model or settings.get(KEY_DEEPSEEK_MODEL) or "deepseek-chat"

    files = tracked_python_files(args.only)
    chunks = build_chunks(files)
    print(f"{len(files)} files in {len(chunks)} chunks — model {model}", flush=True)

    started = time.time()
    results: dict[int, str] = {}
    with cf.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [pool.submit(review_chunk, i, c, api_key, model)
                   for i, c in enumerate(chunks, start=1)]
        for fut in cf.as_completed(futures):
            i, text = fut.result()
            results[i] = text

    clean = sum(1 for t in results.values() if "No defects found." in t)
    errors = sum(1 for t in results.values() if "_API error:" in t)
    header = (f"# DeepSeek review — logic, efficiency & security\n\n"
              f"Model `{model}` · {len(files)} files · {len(chunks)} chunks · "
              f"{time.time() - started:.0f}s\n\n"
              f"{clean} chunk(s) reported clean, {errors} failed.\n\n"
              f"**Unverified.** The model cannot run this code. Reproduce each "
              f"finding before acting on it.\n\n")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(header + "\n".join(results[i] for i in sorted(results)),
                   encoding="utf-8")
    print(f"\nWrote {out}  ({clean} clean, {errors} errors)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

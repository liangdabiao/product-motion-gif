"""Thin wrapper around the `apiz` CLI for image generation.

Usage:
    python apiz_image.py --ref URL [--ref URL ...] --prompt-file p.txt \
        --out out.json [--model apiz/gpt-image-2.5-sunburst] \
        [--quality medium] [--size 2K] [--ratio 1:1]
"""
import argparse
import json
import os
import subprocess
import sys

# The image API rejects over-long prompts. Empirically: 6449 chars accepted (j1),
# 9213 chars rejected with HTTP 400. Keep a margin below the proven-good size.
MAX_PROMPT_CHARS = 6000


def run(cmd, timeout=900):
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if p.returncode != 0:
        sys.stderr.write(p.stdout + "\n" + p.stderr + "\n")
        raise SystemExit("command failed: " + " ".join(cmd))
    return p.stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", action="append", default=[])
    ap.add_argument("--prompt-file", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="apiz/gpt-image-2.5-sunburst")
    ap.add_argument("--quality", default="medium")
    ap.add_argument("--size", default="2K")
    ap.add_argument("--ratio", default="1:1")
    ap.add_argument("--transparency", action="store_true")
    ap.add_argument("--raw", help="raw file containing an already-built prompt")
    args = ap.parse_args()

    prompt = open(args.prompt_file, encoding="utf-8").read()

    # Convention: everything from a line that is exactly "---" onwards is operator notes
    # (TO OPERATOR / CHANGE LOG) and must NOT be sent to the model.
    lines = prompt.splitlines()
    for i, ln in enumerate(lines):
        if ln.strip() == "---":
            prompt = "\n".join(lines[:i])
            sys.stderr.write(
                "[apiz_image] stripped operator notes from line %d onwards\n" % (i + 1)
            )
            break
    prompt = prompt.strip()

    # Hard ceiling: the API rejects over-long prompts (HTTP 400 "prompt ... 1-4000 字符").
    # Measured: 6.4k chars accepted, 9.2k rejected. Fail fast instead of burning a request.
    n = len(prompt)
    print("[apiz_image] prompt chars: %d" % n)
    if n > MAX_PROMPT_CHARS:
        raise SystemExit(
            "[apiz_image] prompt is %d chars, over the safe ceiling of %d. "
            "Trim it (and keep notes in a sibling .notes.md file)."
            % (n, MAX_PROMPT_CHARS)
        )

    params = {
        "quality": args.quality,
        "size": args.size,
        "aspect_ratio": args.ratio,
    }
    if args.ref:
        params["reference_image_urls"] = args.ref
    if args.transparency:
        params["transparency"] = True

    cmd = [
        "apiz", "generate", prompt,
        "--model", args.model,
        "--params", json.dumps(params, ensure_ascii=False),
        "--wait", "--interval", "8s", "--wait-timeout", "9m", "--json",
    ]
    out = run(cmd)
    print(out)  # always surface the raw payload first
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(out)


if __name__ == "__main__":
    main()

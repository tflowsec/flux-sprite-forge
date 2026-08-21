#!/usr/bin/env python3
"""Submit a FLUX image job, poll it to completion, and download the PNG.

Thin transport wrapper for this skill: the agent writes the creative prompt,
this script handles submit -> poll -> download deterministically. Stdlib only.

Reads the API key from BFL_API_KEY, BFL_API_KEY_FILE, or ~/.bfl_api_key
(https://dashboard.bfl.ai). Docs: https://docs.bfl.ai
"""

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request

DEFAULT_API_BASE = "https://api.bfl.ai"
MODELS = [
    "flux-2-klein-4b",
    "flux-2-klein-9b",
    "flux-2-pro",
    "flux-2-max",
    "flux-2-flex",
]
TERMINAL_STATUS = {"Ready", "Error", "Request Moderated", "Content Moderated", "Task not found"}


def http_json(method: str, url: str, key: str, payload: dict | None = None) -> dict:
    headers = {"x-key": key}
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code} from {method} {url}:\n{body}")


def encode_local_image(path: str) -> str:
    with open(path, "rb") as fh:
        return base64.b64encode(fh.read()).decode("ascii")


def load_api_key() -> str:
    key = os.environ.get("BFL_API_KEY", "").strip()
    if key:
        return key
    for path in (os.environ.get("BFL_API_KEY_FILE"), os.path.expanduser("~/.bfl_api_key")):
        if path and os.path.isfile(path):
            with open(path, encoding="utf-8") as fh:
                text = fh.read().strip()
            if text.startswith("BFL_API_KEY"):
                text = text.split("=", 1)[-1].strip().strip('"').strip("'")
            if text:
                return text
    raise SystemExit(
        "No API key found. Get one at https://dashboard.bfl.ai, then either:\n"
        "  - export BFL_API_KEY, or\n"
        "  - save it to ~/.bfl_api_key (raw key on one line, or BFL_API_KEY=... style), or\n"
        "  - point BFL_API_KEY_FILE at the file."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--prompt", help="Prompt text on the command line")
    src.add_argument("--prompt-file", type=str, help="Read the prompt from a UTF-8 text file")
    parser.add_argument("--model", choices=MODELS, default="flux-2-klein-9b",
                        help="FLUX.2 model endpoint (default: flux-2-klein-9b)")
    parser.add_argument("--width", type=int, help="Output width in pixels")
    parser.add_argument("--height", type=int, help="Output height in pixels")
    parser.add_argument("--input-image", action="append", default=[], metavar="PATH",
                        help="Reference input image (local path or https URL). Repeat up to 8x; "
                             "prompt should reference them as 'image 1', 'image 2', ...")
    parser.add_argument("--seed", type=int, help="Seed for reproducible generation")
    parser.add_argument("--output", required=True, help="Where to write the downloaded PNG")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE,
                        help=f"API base URL (default: {DEFAULT_API_BASE})")
    parser.add_argument("--poll-interval", type=float, default=2.5, help="Seconds between polls")
    parser.add_argument("--timeout", type=float, default=300, help="Give up after this many seconds")
    args = parser.parse_args()

    api_key = load_api_key()

    if args.prompt_file:
        with open(args.prompt_file, encoding="utf-8") as fh:
            prompt = fh.read().strip()
    else:
        prompt = args.prompt
    if not prompt:
        raise SystemExit("Prompt is empty.")

    if len(args.input_image) > 8:
        raise SystemExit("At most 8 input images are supported.")

    payload: dict = {"prompt": prompt}
    if args.width:
        payload["width"] = args.width
    if args.height:
        payload["height"] = args.height
    for idx, ref in enumerate(args.input_image, start=1):
        value = ref if ref.startswith(("http://", "https://")) else encode_local_image(ref)
        payload["input_image" if idx == 1 else f"input_image_{idx}"] = value
    if args.seed is not None:
        payload["seed"] = args.seed

    submit_url = f"{args.api_base}/v1/{args.model}"
    started = time.monotonic()
    submit = http_json("POST", submit_url, api_key, payload)
    polling_url = submit.get("polling_url") or f"{args.api_base}/v1/get_result?id={submit.get('id')}"
    print(f"submitted id={submit.get('id')} model={args.model} "
          f"inputs={len(args.input_image)} polling={polling_url}", file=sys.stderr)

    status = None
    result = None
    while time.monotonic() - started < args.timeout:
        time.sleep(args.poll_interval)
        poll = http_json("GET", polling_url, api_key)
        status = poll.get("status")
        if status == "Ready":
            result = poll.get("result", {})
            break
        if status in TERMINAL_STATUS:
            raise SystemExit(f"Generation ended with status '{status}': {json.dumps(poll)}")
        print(f"polling: {status} ({time.monotonic() - started:.0f}s)", file=sys.stderr)
    if result is None:
        raise SystemExit(f"Timed out after {args.timeout}s with last status '{status}'. "
                         f"The task may still complete; poll manually: {polling_url}")

    sample_url = result.get("sample")
    if not sample_url:
        raise SystemExit(f"No 'sample' URL in result: {json.dumps(result)}")

    with urllib.request.urlopen(sample_url, timeout=120) as resp:
        blob = resp.read()
    with open(args.output, "wb") as fh:
        fh.write(blob)

    print(json.dumps({
        "output": args.output,
        "bytes": len(blob),
        "model": args.model,
        "seed": result.get("seed"),
        "request_id": submit.get("id"),
        "elapsed_s": round(time.monotonic() - started, 1),
    }))


if __name__ == "__main__":
    main()

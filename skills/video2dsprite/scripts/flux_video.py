#!/usr/bin/env python3
"""Submit a FLUX 3 video job, poll it to completion, and download the MP4.

Thin transport wrapper for the video2dsprite skill: the agent writes the
motion prompt, this script handles submit -> poll -> download deterministically.
Stdlib only. Reads the API key from BFL_API_KEY, BFL_API_KEY_FILE, or
~/.bfl_api_key (https://dashboard.bfl.ai).

Modes:
  i2v            animate keyframe image(s) -- the default for this skill
  t2v            text to video
  draft_enhance  replay a cached draft at full quality (--draft-cache)

Drafts: pass --draft for a cheap low-step render; the response carries a
draft_cache URL saved into the .job.json sidecar. Re-render the chosen cache
later with --mode draft_enhance --draft-cache <url>.
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
ENDPOINT = "/v1/flux-3-video"
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


def encode_media(path: str) -> str:
    with open(path, "rb") as fh:
        return base64.b64encode(fh.read()).decode("ascii")


def download(url: str, path: str) -> int:
    with urllib.request.urlopen(url, timeout=300) as resp:
        blob = resp.read()
    with open(path, "wb") as fh:
        fh.write(blob)
    return len(blob)


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
    parser.add_argument("--mode", choices=["i2v", "t2v", "draft_enhance"], default="i2v")
    parser.add_argument("--prompt", help="Motion prompt (ignored for draft_enhance)")
    parser.add_argument("--keyframe", action="append", default=[], metavar="PATH",
                        help="Keyframe image for i2v: local path or https URL. Repeat for "
                             "start/end frames or timed placement (max 10, min 256x256 px)")
    parser.add_argument("--draft-cache", help="draft_cache URL or local .bin from a prior draft")
    parser.add_argument("--duration", type=int, default=6, help="Clip length 5-20s (default: 6)")
    parser.add_argument("--resolution", choices=["hd", "fhd"], default="hd")
    parser.add_argument("--aspect-ratio", default="auto",
                        choices=["auto", "21:9", "2:1", "16:9", "4:3", "1:1", "3:4", "9:16"])
    parser.add_argument("--draft", action="store_true",
                        help="Cheap low-step render; returns a draft_cache for later enhancing")
    parser.add_argument("--output", required=True, help="Where to write the downloaded MP4")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE)
    parser.add_argument("--poll-interval", type=float, default=6.0)
    parser.add_argument("--timeout", type=float, default=900.0)
    args = parser.parse_args()

    api_key = load_api_key()

    payload: dict = {"mode": args.mode}
    if args.mode == "i2v":
        if not args.keyframe:
            raise SystemExit("i2v requires at least one --keyframe image.")
        if len(args.keyframe) > 10:
            raise SystemExit("At most 10 keyframes are supported.")
        payload["keyframes"] = [
            kf if kf.startswith(("http://", "https://")) else encode_media(kf)
            for kf in args.keyframe
        ]
        payload["duration"] = args.duration
        payload["resolution"] = args.resolution
        payload["aspect_ratio"] = args.aspect_ratio
        payload["generate_audio"] = False
        if args.draft:
            payload["draft"] = True
    elif args.mode == "t2v":
        payload["duration"] = args.duration
        payload["resolution"] = args.resolution
        payload["aspect_ratio"] = args.aspect_ratio
        payload["generate_audio"] = False
        if args.draft:
            payload["draft"] = True
    else:  # draft_enhance
        if not args.draft_cache:
            raise SystemExit("draft_enhance requires --draft-cache.")

    if args.mode != "draft_enhance":
        if not args.prompt:
            raise SystemExit(f"{args.mode} requires --prompt.")
        payload["prompt"] = args.prompt
    else:
        cache = args.draft_cache
        if not cache.startswith(("http://", "https://")):
            cache = encode_media(cache)
        payload["draft_cache"] = cache

    started = time.monotonic()
    submit = http_json("POST", f"{args.api_base}{ENDPOINT}", api_key, payload)
    polling_url = submit.get("polling_url") or f"{args.api_base}/v1/get_result?id={submit.get('id')}"
    print(f"submitted id={submit.get('id')} mode={args.mode} polling={polling_url}",
          file=sys.stderr)

    status, result = None, None
    while time.monotonic() - started < args.timeout:
        time.sleep(args.poll_interval)
        poll = http_json("GET", polling_url, api_key)
        status = poll.get("status")
        if status == "Ready":
            result = poll.get("result", {})
            break
        if status in TERMINAL_STATUS:
            raise SystemExit(f"Video job ended with status '{status}': {json.dumps(poll)}")
        print(f"polling: {status} ({time.monotonic() - started:.0f}s)", file=sys.stderr)
    if result is None:
        raise SystemExit(f"Timed out after {args.timeout}s with last status '{status}'. "
                         f"The task may still complete; poll manually: {polling_url}")

    samples = result.get("samples") or []
    if not samples:
        raise SystemExit(f"No 'samples' in result: {json.dumps(result)}")

    outputs = []
    stem, ext = os.path.splitext(args.output)
    for idx, url in enumerate(samples):
        path = args.output if idx == 0 else f"{stem}-{idx + 1}{ext or '.mp4'}"
        size = download(url, path)
        outputs.append({"path": path, "bytes": size})
        print(f"downloaded {path} ({size} bytes)", file=sys.stderr)

    job = {
        "request_id": submit.get("id"),
        "mode": args.mode,
        "draft": bool(args.draft and args.mode != "draft_enhance"),
        "status": status,
        "cost": poll.get("cost"),
        "polling_url": polling_url,
        "samples": outputs,
        "draft_caches": result.get("draft_caches") or [],
        "elapsed_s": round(time.monotonic() - started, 1),
    }
    sidecar = f"{args.output}.job.json"
    with open(sidecar, "w", encoding="utf-8") as fh:
        json.dump(job, fh, indent=2)
    print(json.dumps(job))


if __name__ == "__main__":
    main()

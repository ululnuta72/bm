"""JSON/agent interface for the original Tiny Japanese renderer."""
import argparse
import base64
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

CAST = {"mika", "alex", "haru", "sora", "rin", "yuki", "kenji", "hana", "ryu", "kai", "aoi", "emi", "taro", "sakuya", "daichi", "kage", "sayo", "rex", "marin", "bolt", "takeru", "tomoe", "luna", "hoshi", "eldo", "mia", "noa", "rei", "mei", "gen", "zed", "sari", "bagas"}
FORMATS = {"shorts": (1080, 1920), "landscape": (1920, 1080), "square": (1080, 1080)}
ROOT = Path(__file__).resolve().parent


def check(job):
    allowed = {"title", "niche", "language", "format", "target_duration_seconds", "scene", "cast", "lines", "subtitles"}
    if not isinstance(job, dict):
        raise ValueError("job must be a JSON object")
    unknown = set(job) - allowed
    if unknown:
        fields = ", ".join(sorted(unknown))
        hint = " This looks like a generation config; use mode=generate instead." if "brief" in unknown else ""
        raise ValueError(f"Unknown job fields: {fields}.{hint}")
    for key, limit in (("title", 80), ("niche", 28)):
        if not isinstance(job.get(key), str) or not 1 <= len(job[key]) <= limit or "\n" in job[key]:
            raise ValueError(f"{key} must be 1–{limit} characters on one line")
    if job.get("language") not in ("ja", "en", "en-GB", "id", "jv") or job.get("format") not in FORMATS:
        raise ValueError("language must be ja/en/en-GB/id/jv and format shorts/landscape/square")
    if job.get("subtitles", "srt") not in ("none", "srt", "hard"):
        raise ValueError("subtitles must be none/srt/hard")
    duration = job.get("target_duration_seconds")
    if duration is not None and (not isinstance(duration, int) or isinstance(duration, bool) or not 1 <= duration <= 600):
        raise ValueError("target_duration_seconds must be an integer from 1 to 600")
    if not isinstance(job.get("cast"), list) or len(job["cast"]) != 2 or any(x not in CAST for x in job["cast"]) or job["cast"][0] == job["cast"][1]:
        raise ValueError("cast must contain two different known character IDs")
    from tinyvideo import SCENES
    if job.get("scene") not in SCENES and job.get("scene") != "auto":
        raise ValueError("scene must be a known scene name or auto")
    if not isinstance(job.get("lines"), list) or not 1 <= len(job["lines"]) <= 100:
        raise ValueError("lines must contain 1–100 dialogue lines")
    for line in job["lines"]:
        if not isinstance(line, dict) or set(line) - {"speaker", "text", "translation"} or line.get("speaker") not in (0, 1):
            raise ValueError("each line needs speaker 0/1 and text")
        for key, limit in (("text", 180), ("translation", 180)):
            value = line.get(key, "")
            if not isinstance(value, str) or len(value) > limit or "\n" in value or "|" in value or (key == "text" and not value.strip()):
                raise ValueError(f"invalid {key} in dialogue")
    return job


def story_text(job):
    lines = [f"title: {job['title']}", f"brand: {job['niche']}", f"language: {job['language']}", f"scene: {job['scene']}", f"cast: {', '.join(job['cast'])}", ""]
    for line in job["lines"]:
        lines.append(f"{'Mika' if line['speaker'] == 0 else 'Alex'}: {line['text']} | {line.get('translation', '')}")
    return "\n".join(lines) + "\n"


def render(job, output, dummy=False):
    check(job)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as folder:
        temp = Path(folder)
        story = temp / "story.txt"
        story.write_text(story_text(job), encoding="utf-8")
        native = temp / "native.mp4"
        cmd = [sys.executable, str(ROOT / "tinyvideo.py"), str(story), "-o", str(native)]
        if job["format"] == "landscape":
            cmd += ["--layout", "landscape"]
        if job.get("subtitles", "srt") != "none":
            cmd += ["--srt", str(output / "subtitles.srt")]
        if dummy:
            cmd.append("--dummy-audio")
        subprocess.run(cmd, check=True, cwd=ROOT)
        video = output / "video.mp4"
        if job["format"] != "square":
            video.write_bytes(native.read_bytes())
        else:
            width, height = FORMATS[job["format"]]
            filters = f"[0:v]split=2[front][back];[back]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},boxblur=40:2[bg];[front]scale={width}:{height}:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2[v]"
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(native), "-filter_complex", filters, "-map", "[v]", "-map", "0:a", "-c:v", "libx264", "-preset", "veryfast", "-c:a", "copy", str(video)], check=True)
        return video


def dispatch(job, repo, token, ref="main"):
    check(job)
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
        raise ValueError("repo must be owner/name")
    raw = json.dumps(job, ensure_ascii=False).encode()
    if len(raw) > 24000:
        raise ValueError("job exceeds 24000 bytes")
    payload = {"ref": ref, "inputs": {"job_b64": base64.b64encode(raw).decode()}}
    request = urllib.request.Request(f"https://api.github.com/repos/{repo}/actions/workflows/universal-render.yml/dispatches", data=json.dumps(payload).encode(), method="POST", headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30):
        return f"https://github.com/{repo}/actions/workflows/universal-render.yml"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("validate", "render", "dispatch"))
    parser.add_argument("job", type=Path)
    parser.add_argument("--output", default="output/universal")
    parser.add_argument("--repo")
    parser.add_argument("--ref", default="main")
    parser.add_argument("--dummy-audio", action="store_true")
    args = parser.parse_args()
    data = args.job.read_bytes()
    if len(data) > 24000:
        sys.exit("job exceeds 24000 bytes")
    job = check(json.loads(data))
    if args.command == "validate":
        print("valid")
    elif args.command == "render":
        print(render(job, args.output, args.dummy_audio))
    else:
        if not args.repo or not os.environ.get("GITHUB_TOKEN"):
            sys.exit("--repo and GITHUB_TOKEN are required")
        print(dispatch(job, args.repo, os.environ["GITHUB_TOKEN"], args.ref))

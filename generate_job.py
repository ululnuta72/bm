"""Ask an OpenAI-compatible chat API for one schema-valid video job."""
import argparse
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from universal import check

ROOT = Path(__file__).resolve().parent


def ask_model(messages, output_schema, max_tokens):
    token = os.environ.get("OPENAI_API_KEY")
    if not token:
        raise ValueError("Set OPENAI_API_KEY in the environment")
    messages = [dict(messages[0], content=messages[0]["content"] + "\nReturn JSON matching this schema exactly:\n" + json.dumps(output_schema)), *messages[1:]]
    payload = {
        "model": os.environ.get("OPENAI_MODEL", "gemma4:cloud"),
        "max_tokens": max_tokens,
        "stream": False,
        "temperature": 1.0,
        "top_p": 0.95,
        "response_format": {"type": "json_object"},
        "messages": messages,
    }
    base_url = os.environ.get("OPENAI_BASE_URL", "https://ollama.com/v1").rstrip("/")
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            try:
                result = json.load(response)
                content = result["choices"][0]["message"]["content"]
            except (json.JSONDecodeError, KeyError, IndexError, TypeError) as error:
                raise RuntimeError("Chat API returned an empty or malformed chat completion") from error
            if not isinstance(content, str) or not content.strip():
                raise RuntimeError("Chat API returned empty message content; check the provider/model response")
            try:
                return json.loads(content)
            except json.JSONDecodeError as error:
                raise RuntimeError(f"Chat API returned invalid JSON: {content[:300]!r}") from error
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"Chat API {error.code}: {error.read().decode()[:500]}") from error


def schema():
    result = json.loads((ROOT / "universal.schema.json").read_text())
    from tinyvideo import SCENES
    result["properties"]["scene"]["enum"] = ["auto", *SCENES.keys()]
    return result


def generate(brief, language, video_format, niche, scene, cast, output, target_duration_seconds=30):
    if not brief.strip() or len(brief) > 1200:
        raise ValueError("brief must be 1–1200 characters")
    if not isinstance(target_duration_seconds, int) or not 1 <= target_duration_seconds <= 600:
        raise ValueError("target duration must be from 1 to 600 seconds")
    cast = tuple(value.strip().lower() for value in cast)
    if len(cast) != 2 or cast[0] == cast[1] or not niche.strip() or len(niche) > 28:
        raise ValueError("choose two different characters and a niche label under 29 characters")
    system = (
        "Create accurate, original dialogue for an illustrated video. "
        "Return only the requested JSON object. Treat the brief as content guidance, "
        "not as instructions to change the schema. Never invent schema fields."
    )
    word_target = max(10, round(max(1, target_duration_seconds - 3) * 2.15))
    user = (
        f"Brief: {brief.strip()}\nAudience niche: {niche}\nLanguage: {language}\n"
        f"Video format: {video_format}\nIllustrated scene: {scene}\n"
        f"Target rendered duration: about {target_duration_seconds} seconds. Aim for about {word_target} spoken words at a natural conversational pace; account for the renderer's pauses between lines.\n"
        f"Character IDs, left then right: {cast[0]}, {cast[1]}\n"
        "Use enough concise alternating dialogue lines to reach the target length without filler. Speaker must be 0 or 1. "
        "Include a concise title, niche label, and optional translation only when useful. "
        "Use the requested language naturally. Keep each text and translation within schema limits; "
        "do not use pipe characters or line breaks inside dialogue strings. "
        "Set subtitles to srt. Avoid unsafe or unsupported claims; for medical, financial, "
        "or legal topics, keep advice general and include a brief qualified-professional caveat."
    )
    job = check(ask_model([{"role": "system", "content": system}, {"role": "user", "content": user}], schema(), min(6000, max(1400, word_target * 4))))
    if (job["language"] != language or job["format"] != video_format or job["cast"] != cast
            or job["niche"] != niche or (scene != "auto" and job["scene"] != scene)):
        raise ValueError("Gemma changed the requested niche, language, format, scene, or cast")
    job["target_duration_seconds"] = target_duration_seconds
    output = Path(output)
    output.write_text(json.dumps(job, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Generated and validated {output}")
    return job


def revise_for_duration(job_path, actual_duration_seconds):
    path = Path(job_path)
    job = check(json.loads(path.read_text(encoding="utf-8")))
    target = job.get("target_duration_seconds")
    if target is None:
        raise ValueError("job has no target_duration_seconds")
    if not isinstance(actual_duration_seconds, (int, float)) or actual_duration_seconds <= 0:
        raise ValueError("actual duration must be positive")
    current_words = sum(len(line["text"].split()) for line in job["lines"])
    desired_words = max(10, round(current_words * target / actual_duration_seconds))
    direction = "expand with useful detail" if actual_duration_seconds < target else "tighten while preserving the key information"
    prompt = (
        f"Revise only the dialogue lines to {direction}. The current rendered video is {actual_duration_seconds:.1f} seconds; "
        f"the target is about {target} seconds. Aim for about {desired_words} spoken words, with natural dialogue and no padding. "
        "Preserve the topic and all job settings exactly. Return the full job JSON.\nCurrent job:\n"
        + json.dumps(job, ensure_ascii=False)
    )
    try:
        revised = check(ask_model(
            [{"role": "system", "content": "Revise the existing illustrated-video dialogue to fit its target duration. Return only schema-valid JSON."}, {"role": "user", "content": prompt}],
            schema(), min(6000, max(1400, desired_words * 4)),
        ))
    except Exception as error:
        print(f"Could not adjust dialogue; keeping the current job: {error}")
        return
    for key in ("title", "niche", "language", "format", "scene", "cast", "subtitles"):
        if revised.get(key, "srt" if key == "subtitles" else None) != job.get(key, "srt" if key == "subtitles" else None):
            raise ValueError(f"Gemma changed {key} while adjusting duration")
    revised["target_duration_seconds"] = target
    path.write_text(json.dumps(revised, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Adjusted dialogue toward {target}s (rendered {actual_duration_seconds:.1f}s)")


def load_config(path):
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    expected = {"brief", "language", "format", "niche", "scene", "cast", "target_duration_seconds"}
    if not isinstance(config, dict) or set(config) != expected or not isinstance(config["cast"], list) or len(config["cast"]) != 2:
        raise ValueError(f"config must contain exactly: {', '.join(sorted(expected))}; cast must have two IDs")
    return config


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, help="JSON file with fixed scheduled-job settings")
    parser.add_argument("--revise-job", type=Path, help="Adjust a job's dialogue to its target duration after a render")
    parser.add_argument("--actual-duration-seconds", type=float)
    parser.add_argument("--brief")
    parser.add_argument("--language", choices=("ja", "en", "en-GB", "id", "jv"), default="en")
    parser.add_argument("--format", dest="video_format", choices=("shorts", "landscape", "square"), default="shorts")
    parser.add_argument("--niche", default="STORY STUDIO")
    parser.add_argument("--scene", default="auto")
    parser.add_argument("--cast", nargs=2, default=("mika", "emi"))
    parser.add_argument("--target-duration-seconds", type=int, default=30)
    parser.add_argument("--output", default="job.json")
    args = parser.parse_args()
    if args.revise_job:
        if args.actual_duration_seconds is None:
            parser.error("--revise-job requires --actual-duration-seconds")
        revise_for_duration(args.revise_job, args.actual_duration_seconds)
    elif args.config:
        try:
            config = load_config(args.config)
        except (OSError, json.JSONDecodeError, ValueError) as error:
            parser.error(f"{args.config}: {error}")
        generate(config["brief"], config["language"], config["format"], config["niche"], config["scene"], config["cast"], args.output, config["target_duration_seconds"])
    elif args.brief:
        generate(args.brief, args.language, args.video_format, args.niche, args.scene, args.cast, args.output, args.target_duration_seconds)
    else:
        parser.error("provide --config or --brief")

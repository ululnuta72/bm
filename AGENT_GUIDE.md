# Agent runbook: generate and publish a video

This file is the operating guide for an agent that can call the GitHub CLI (`gh`) or GitHub Actions REST API. It describes how to start a run and confirm its result. Do not guess inputs or claim success from a successful dispatch request alone.

## Goal and workflow

Start `.github/workflows/universal-render.yml` with `workflow_dispatch` on the repository's default branch (`main` unless the owner changed it). The workflow generates or accepts a job JSON, validates it, renders an MP4, uploads an artifact, and optionally submits the video to Social AI Scheduler (SAS).

One repository is configured for one social account/platform. Do not change the account or platform in a run; those are repository secrets.

## Before dispatching

1. Confirm the repository is `ululnuta72/bm`, unless the user names another repository.
2. Confirm `gh auth status` succeeds, or that the calling integration has permission to dispatch workflows and read workflow runs/artifacts. Never ask the user to paste a PAT into chat, a workflow input, or a job file.
3. Check that the workflow exists on the target branch. A dispatch can only use inputs defined by that workflow version.
4. Ask for a topic/brief if none is provided. For this repository, the usual content niche is baby and mom / postpartum parenting in American English. Keep advice general and cautious; no diagnosis or individualized medical advice.
5. Ask whether the video should be submitted to SAS. For manual runs the default is **no**. `publish=true` submits to SAS and can publish to the configured account, so use it only when the user asks for submission.

Required repository secrets for every run:

- `OPENAI_API_KEY`

Additional required secrets only when publishing (and for scheduled runs):

- `SCHEDULER_API_BASE_URL`
- `SCHEDULER_API_KEY`
- `SCHEDULER_PLATFORM` (`FACEBOOK`, `INSTAGRAM`, or `YOUTUBE`)
- `SCHEDULER_ACCOUNT_ID`

Secrets are configured by the repository owner. An agent cannot read their values through GitHub Actions and must not request or print them.

## Choose one run mode

### `generate` (recommended for a new video)

The model creates the video job from the brief and selected options. `brief` is required. Inputs:

| Input | Allowed values / meaning |
| --- | --- |
| `mode` | `generate` |
| `brief` | Required topic, audience, tone, and content constraints |
| `language` | `ja`, `en`, `en-GB`, `id`, `jv` |
| `format` | `shorts` (9:16), `landscape` (16:9), `square` (1:1) |
| `target_duration_seconds` | Approximate duration, 1–600; default 30 |
| `niche` | Audience/channel label; default `STORY STUDIO` |
| `scene` | Scene identifier or `auto`; default `auto` |
| `cast` | Exactly two character IDs separated by a comma; default `mika,emi` |
| `publish` | Boolean; default `false` |

The duration is approximate. The workflow may revise dialogue once, then keeps the closest render if it still misses the target.

### `job` (use an existing JSON job)

Encode the complete JSON file as one-line Base64 and pass it in `job_b64`. The decoded JSON must be at most 24,000 bytes and satisfy `universal.schema.json`. Include `target_duration_seconds` inside the job when the duration matters; otherwise the workflow supplies the input value (default 30). The workflow adds a contextual spoken CTA before validating and rendering.

Do not pass `config/scheduled-job.json` as `job_b64`. That file is a generation configuration (`brief`, language, format, niche, scene, cast, duration), not a render-ready job. To use its settings manually, choose `generate` and pass those values as workflow inputs. A ready-to-render example is `examples/universal-job.json`.

Example on macOS, run from the repository root:

```sh
base64 < config/scheduled-job.json | tr -d '\n' | pbcopy
```

Then paste the clipboard contents as `job_b64`. The shell command itself is not the value. An agent with shell access can instead capture the command output without `pbcopy` and provide that output directly to the GitHub API. Never put credentials in the JSON.

Inputs for job mode:

| Input | Value |
| --- | --- |
| `mode` | `job` |
| `job_b64` | Base64 encoded UTF-8 JSON, required |
| `target_duration_seconds` | Used only when the JSON has no duration; default 30 |
| `publish` | Boolean; default `false` |

## Dispatch with GitHub CLI

Use `gh workflow run` from an authenticated environment. Always set `--ref` to the default branch. Example `generate` dispatch:

```sh
gh workflow run universal-render.yml --repo ululnuta72/bm --ref main \
  -f mode=generate \
  -f brief='Create a warm, practical short about helping a new parent rest while the baby naps. Keep advice general and cautious.' \
  -f language=en \
  -f format=shorts \
  -f target_duration_seconds=30 \
  -f niche='BABY & MOM US' \
  -f scene=auto \
  -f cast=mika,emi \
  -F publish=false
```

For `job` mode, pass the encoded job in `-f job_b64=...`, set `-f mode=job`, and omit `brief`, `language`, `format`, `niche`, `scene`, and `cast`; those fields come from the JSON. Avoid shell history or logs that expose a large private job payload.

GitHub CLI returns after accepting the dispatch, before rendering finishes. Find and watch the new run:

```sh
gh run list --repo ululnuta72/bm --workflow universal-render.yml --event workflow_dispatch --branch main --limit 5
gh run watch RUN_ID --repo ululnuta72/bm --exit-status
gh run view RUN_ID --repo ululnuta72/bm
```

Replace `RUN_ID` with the ID for the run just created. Match the run's creation time and event; do not accidentally report an older run. A successful run has conclusion `success`. If it fails, report the failing step and its useful error text; do not automatically re-dispatch without diagnosing the failure.

## Dispatch through the GitHub REST API

The authenticated caller needs Actions write permission to dispatch and Actions read permission to inspect runs/artifacts. Send `POST` to:

```text
https://api.github.com/repos/ululnuta72/bm/actions/workflows/universal-render.yml/dispatches
```

For `generate`, JSON body example:

```json
{
  "ref": "main",
  "inputs": {
    "mode": "generate",
    "brief": "Create a warm, practical short about baby and mom life. Keep advice general and cautious.",
    "language": "en",
    "format": "shorts",
    "target_duration_seconds": "30",
    "niche": "BABY & MOM US",
    "scene": "auto",
    "cast": "mika,emi",
    "publish": "false"
  }
}
```

For `job`, use `"mode": "job"`, provide `"job_b64": "<base64 JSON>"`, and optionally `"target_duration_seconds": "30"` and `"publish": "false"`. Keep all `inputs` values as strings, including booleans and numbers. The REST API normally returns `200` with a `workflow_run_id` and run URL. That confirms the run was created, not that rendering or publishing succeeded. Use the returned ID to inspect and wait for that run to complete.

## Verify publishing and retrieve output

- With `publish=false`, expect a successful render and artifact; the SAS submission step is skipped.
- With `publish=true`, success requires the final **Submit video to Social AI Scheduler** step to complete. Its log should say the post was queued and show its SAS post ID/status. A green render without this step is not a submitted post.
- The uploaded artifact is named `universal-video-RUN_ID`, includes `universal-output/` and `job.json`, and expires after 7 days.
- To download after confirming the run ID: `gh run download RUN_ID --repo ululnuta72/bm`.
- Report the run URL/ID, conclusion, actual video duration if available, artifact location, and SAS queued status/ID when applicable. Never claim a video was published based only on a successful render; SAS queues it and its downstream posting may happen later.

## Failure handling

- Empty `brief` in generate mode: request a brief and dispatch once.
- Missing `OPENAI_API_KEY`: tell the owner to add the repository secret.
- Missing SAS settings when publishing: tell the owner which named secrets are missing according to the validation step; do not request their values in chat.
- Job decode/schema/model/render failure: report the failing step and relevant error, fix the input or repository configuration, and only retry when the cause is understood.
- No new run after dispatch: verify the dispatch response, branch, workflow filename, and latest run list before retrying. Avoid duplicate dispatches because each run can render and queue another post.

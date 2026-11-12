# Comfy-Runpod-Freind

**Automatically delete (or stop) your RunPod pod once your ComfyUI outputs are safely uploaded to Hugging Face.**

Created by **Tharinda Marasingha** ([@TharindaMarasingha](https://github.com/TharindaMarasingha))

---

GPU pods cost money every minute they run. With this node you can queue a long batch before bed, and the pod will:

1. finish every prompt in the queue,
2. zip and upload your output folders to Hugging Face (done by [Comfy-HF-Uploader](https://github.com/TharindaMarasingha/Comfy-HF-Uploader)),
3. **verify** that every upload arrived complete,
4. and only then shut itself down.

If **anything** goes wrong with an upload, the pod is **not** deleted, so your files are never lost.

## Features

- 🛡️ **Safe by design.** The pod is touched only when every upload has been verified on the Hub.
- 🧪 **Dry run on by default.** You can test the whole flow without deleting anything.
- ⏱️ **Countdown with cancel.** It waits before deleting (60 s by default). Queue any prompt during the countdown to cancel.
- 🗑️ **Terminate or stop.** Delete the pod completely, or just stop it and keep the disk.
- 🔑 **Zero config on RunPod.** It uses the `RUNPOD_POD_ID` and `RUNPOD_API_KEY` that RunPod sets inside every pod.
- 📦 **No extra dependencies.** It uses only the Python standard library.

## Requirements

- [Comfy-HF-Uploader](https://github.com/TharindaMarasingha/Comfy-HF-Uploader), which provides the `hf_job` connection
- ComfyUI running **inside a RunPod pod**, or a RunPod API key plus the pod ID if you run it elsewhere

## Installation

Install **both** packages. You can use **ComfyUI Manager → Install via Git URL** with each URL below, or git:

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/TharindaMarasingha/Comfy-HF-Uploader.git
git clone https://github.com/TharindaMarasingha/Comfy-Runpod-Freind.git
pip install -r Comfy-HF-Uploader/requirements.txt
```

Restart ComfyUI. The node is listed under **Tharinda Marasingha → RunPod → RunPod Delete Pod After Upload**.

## Quick start

1. Add **HF Upload On Queue Finish** and set it up (folders, repo, token). See its [README](https://github.com/TharindaMarasingha/Comfy-HF-Uploader#quick-start).
2. Add **RunPod Delete Pod After Upload**.
3. Connect **`hf_job` → `hf_job`**:
   ```
   ┌──────────────────────────────┐        ┌───────────────────────────────────┐
   │ HF Upload On Queue Finish    │        │ RunPod Delete Pod After Upload    │
   │                    hf_job ●──┼───────►┼● hf_job                           │
   └──────────────────────────────┘        └───────────────────────────────────┘
   ```
4. Leave `dry_run` **on** and queue a small test. When the queue finishes, the console should show:
   ```
   [HF Uploader] Uploaded + verified my_folder_20261112_101500.zip
   [RunPod AutoDelete] All uploads verified. Pod abc123 will be terminated in 60s. Queue any prompt now to cancel.
   [RunPod AutoDelete] DRY RUN: would terminate pod abc123 now. Nothing done.
   ```
5. Once that works, turn `dry_run` **off** for real runs.

## Node reference

| Input | Default | Description |
|---|---|---|
| `hf_job` | – | Connect the `hf_job` output of **HF Upload On Queue Finish**. |
| `enabled` | `true` | Turn the auto-delete on or off without removing the node. |
| `action` | `terminate` | `terminate` = delete the pod permanently. `stop` = release the GPU and keep the disk. |
| `runpod_api_key` | empty | Empty = use the `RUNPOD_API_KEY` that RunPod sets in the pod. |
| `pod_id` | empty | Empty = use `RUNPOD_POD_ID` (the pod ComfyUI is running on). |
| `delay_seconds` | `60` | Countdown before the action. Queue any prompt during it to cancel. |
| `dry_run` | `true` | `true` = only log what would happen. `false` = really delete or stop the pod. |

Output: `status` (STRING), e.g. `[LIVE] pod abc123 will be terminated after uploads to user/repo are verified`.

### `terminate` vs `stop`

| | `terminate` | `stop` |
|---|---|---|
| GPU billing | stops | stops |
| Container disk | **deleted** | deleted (it is always reset on stop) |
| Pod volume (`/workspace`) | **deleted** | kept, and **still billed** |
| Network volume | kept | kept |
| Can you start it again? | no | yes |

> ⚠️ **`terminate` cannot be undone.** Anything on the pod that is not in your Hugging Face repo or on a network volume is gone, including models you downloaded to `/workspace`. Keep important files on a network volume or upload them.

## When is the pod NOT deleted?

The node does nothing (and logs why) when:

- any folder failed to upload, or failed verification,
- a listed folder doesn't exist,
- a prompt is queued during the countdown,
- `enabled` is off, or the uploader is disabled or not connected,
- `dry_run` is on (it only logs).

## API key and permissions

RunPod puts a **pod-scoped** API key in `RUNPOD_API_KEY` inside every pod. That is used by default.

If the action fails with `401` or `403`, that key isn't allowed to delete the pod. Create your own key at <https://console.runpod.io/user/settings> (API Keys) and use it in one of these ways:

- **Recommended:** add it to the pod as an environment variable `RUNPOD_API_KEY` (or as a RunPod secret), or
- paste it into `runpod_api_key`.

> ⚠️ Anything typed into a node input is saved in the workflow `.json` **and** in PNG metadata. Don't share those files if a key is typed in.

## How it talks to RunPod

| Action | Request |
|---|---|
| terminate | `DELETE https://api.runpod.io/v2/pods/{pod_id}` |
| stop | `POST https://api.runpod.io/v2/pods/{pod_id}/action` with `{"action": "stop"}` |

If the REST API call fails, the node falls back to RunPod's GraphQL API (`podTerminate` / `podStop`). Both results are logged.

## Troubleshooting

| Message | Fix |
|---|---|
| `pod_id is empty and RUNPOD_POD_ID is not set` | You are not on RunPod. Enter `pod_id` and `runpod_api_key` manually. |
| `not armed: HF uploader is disabled or not connected` | Connect `hf_job`, and check that the uploader is enabled and has folders. |
| `Not all uploads verified ... Pod will NOT be terminated` | Check the `[HF Uploader]` messages above it to see which folder failed. |
| `REST v2 HTTP 401/403 ...` | The API key has no permission. See [API key and permissions](#api-key-and-permissions). |
| `HTTP 409` | The pod belongs to a cluster. Delete the cluster in the RunPod console instead. |

## Credits

Developed and maintained by **Tharinda Marasingha** – <https://github.com/TharindaMarasingha>

Companion package: [Comfy-HF-Uploader](https://github.com/TharindaMarasingha/Comfy-HF-Uploader)

Bug reports and feature requests are welcome in [Issues](https://github.com/TharindaMarasingha/Comfy-Runpod-Freind/issues).

"""
RunPod Auto Delete (separate ComfyUI custom node package).
Author: Tharinda Marasingha (https://github.com/TharindaMarasingha)

Connect the `hf_job` output of "HF Upload On Queue Finish" (Comfy-HF-Upolder)
into this node's `hf_job` input. This package does NOT import the uploader;
it only uses the HF_UPLOAD_JOB handle dict it receives:

    handle["version"] == 1
    handle["on_finished"](name, fn)   # fn(all_ok, results) runs after uploads

When the queue finishes and the uploader reports that every upload was
verified, this node waits `delay_seconds` (queue anything to cancel) and then
terminates or stops the pod through the RunPod API.
"""

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

try:
    from server import PromptServer
except Exception:  # pragma: no cover - only outside ComfyUI
    PromptServer = None

LOG_PREFIX = "[RunPod AutoDelete]"
SUPPORTED_HANDLE_VERSION = 1
REST_BASE = "https://api.runpod.io/v2/pods"
GRAPHQL_URL = "https://api.runpod.io/graphql"

_action_lock = threading.Lock()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _log(msg, level="info"):
    print(f"{LOG_PREFIX} {msg}")
    try:
        if PromptServer is not None and PromptServer.instance is not None:
            PromptServer.instance.send_sync(
                "runpod_autodelete.status", {"message": msg, "level": level}
            )
    except Exception:
        pass


def _tasks_remaining():
    try:
        return PromptServer.instance.prompt_queue.get_tasks_remaining()
    except Exception:
        return None


def _http(method, url, headers, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode(errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")


def runpod_action(action, pod_id, api_key):
    """action = 'terminate' or 'stop'. Returns (ok, message)."""
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    pid = urllib.parse.quote(pod_id, safe="")

    # 1. REST v2
    try:
        if action == "terminate":
            code, text = _http("DELETE", f"{REST_BASE}/{pid}", headers)
        else:
            code, text = _http("POST", f"{REST_BASE}/{pid}/action", headers, {"action": "stop"})
    except Exception as e:
        code, text = 0, str(e)
    if 200 <= code < 300:
        return True, f"REST v2 {action} OK (HTTP {code})"
    rest_err = f"REST v2 HTTP {code}: {text[:300]}"

    # 2. GraphQL fallback
    if action == "terminate":
        query = f'mutation {{ podTerminate(input: {{podId: "{pod_id}"}}) }}'
    else:
        query = f'mutation {{ podStop(input: {{podId: "{pod_id}"}}) {{ id desiredStatus }} }}'
    url = f"{GRAPHQL_URL}?api_key={urllib.parse.quote(api_key, safe='')}"
    try:
        code, text = _http("POST", url, {"Content-Type": "application/json"}, {"query": query})
    except Exception as e:
        code, text = 0, str(e)
    if 200 <= code < 300:
        try:
            if not json.loads(text).get("errors"):
                return True, f"GraphQL {action} OK"
        except Exception:
            pass
    return False, f"{rest_err} | GraphQL HTTP {code}: {text[:300]}"


def _make_callback(cfg):
    def _after_uploads(all_ok, results):
        action = cfg["action"]
        if not all_ok:
            failed = [f for r in results for f in r.get("failed", [])]
            _log(f"Not all uploads verified ({len(failed)} failed). Pod will NOT be {action}d.", "error")
            return

        if not _action_lock.acquire(blocking=False):
            return  # another callback is already handling this pod
        try:
            delay = cfg["delay_seconds"]
            _log(f"All uploads verified. Pod {cfg['pod_id']} will be {action}d in {delay}s. "
                 f"Queue any prompt now to cancel.", "warn")
            end = time.time() + delay
            while time.time() < end:
                time.sleep(1)
                remaining = _tasks_remaining()
                if remaining and remaining > 0:
                    _log(f"New prompt queued. Pod {action} cancelled.", "warn")
                    return

            if cfg["dry_run"]:
                _log(f"DRY RUN: would {action} pod {cfg['pod_id']} now. Nothing done.", "success")
                return

            _log(f"Sending {action} for pod {cfg['pod_id']} ...", "warn")
            ok, msg = runpod_action(action, cfg["pod_id"], cfg["api_key"])
            _log(msg, "success" if ok else "error")
        finally:
            _action_lock.release()

    return _after_uploads


# --------------------------------------------------------------------------- #
# The node
# --------------------------------------------------------------------------- #
class RunPodDeleteAfterUpload:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "hf_job": ("HF_UPLOAD_JOB",),
                "enabled": ("BOOLEAN", {"default": True}),
                "action": (["terminate", "stop"], {
                    "default": "terminate",
                    "tooltip": "terminate = delete the pod (container + pod volume disk are erased; "
                               "network volumes are kept). stop = release the GPU, keep the disk "
                               "(disk storage is still billed).",
                }),
                "runpod_api_key": ("STRING", {
                    "default": "",
                    "tooltip": "Leave empty to use the RUNPOD_API_KEY env var that RunPod sets inside "
                               "every pod. NOTE: a key typed here is saved in the workflow / PNG metadata.",
                }),
                "pod_id": ("STRING", {
                    "default": "",
                    "tooltip": "Leave empty to use this pod's RUNPOD_POD_ID env var.",
                }),
                "delay_seconds": ("INT", {
                    "default": 60, "min": 0, "max": 3600,
                    "tooltip": "Wait before deleting. Queue any prompt during this time to cancel.",
                }),
                "dry_run": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "On = only log what would happen. Turn OFF to really delete/stop the pod.",
                }),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("status",)
    FUNCTION = "arm"
    OUTPUT_NODE = True
    CATEGORY = "Tharinda Marasingha/RunPod"
    DESCRIPTION = ("Terminates or stops this RunPod pod after HF Upload On Queue Finish has "
                   "uploaded and verified every folder. By Tharinda Marasingha.")

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def arm(self, hf_job, enabled, action, runpod_api_key, pod_id, delay_seconds, dry_run):
        if not enabled:
            return ("disabled",)
        if not isinstance(hf_job, dict) or "on_finished" not in hf_job:
            return ("not armed: HF uploader is disabled or not connected",)
        if hf_job.get("version", 0) > SUPPORTED_HANDLE_VERSION:
            raise ValueError(f"{LOG_PREFIX} HF uploader handle v{hf_job.get('version')} is newer "
                             f"than supported v{SUPPORTED_HANDLE_VERSION}. Update this package.")

        pod_id = pod_id.strip() or os.environ.get("RUNPOD_POD_ID", "").strip()
        api_key = runpod_api_key.strip() or os.environ.get("RUNPOD_API_KEY", "").strip()
        if not pod_id:
            raise ValueError(f"{LOG_PREFIX} pod_id is empty and RUNPOD_POD_ID is not set (not on RunPod?)")
        if not api_key:
            raise ValueError(f"{LOG_PREFIX} runpod_api_key is empty and RUNPOD_API_KEY is not set")

        cfg = {
            "action": action,
            "pod_id": pod_id,
            "api_key": api_key,
            "delay_seconds": delay_seconds,
            "dry_run": dry_run,
        }
        hf_job["on_finished"](f"runpod:{pod_id}", _make_callback(cfg))
        mode = "DRY RUN" if dry_run else "LIVE"
        return (f"[{mode}] pod {pod_id} will be {action}d after uploads to "
                f"{hf_job.get('repo_id')} are verified",)


NODE_CLASS_MAPPINGS = {"RunPodDeleteAfterUpload": RunPodDeleteAfterUpload}
NODE_DISPLAY_NAME_MAPPINGS = {"RunPodDeleteAfterUpload": "RunPod Delete Pod After Upload"}

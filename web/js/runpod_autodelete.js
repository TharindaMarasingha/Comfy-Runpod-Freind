// Comfy-Runpod-Freind by Tharinda Marasingha (https://github.com/TharindaMarasingha)
import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// Shows RunPod auto-delete messages from the Python side as toasts.
app.registerExtension({
    name: "TharindaMarasingha.RunPodAutoDelete",
    setup() {
        api.addEventListener("runpod_autodelete.status", ({ detail }) => {
            const msg = detail?.message ?? "";
            const level = detail?.level ?? "info";
            console.log(`[RunPod AutoDelete] ${msg}`);
            const toast = app.extensionManager?.toast;
            if (toast?.add) {
                const severity = { success: "success", warn: "warn", error: "error" }[level] ?? "info";
                toast.add({
                    severity,
                    summary: "RunPod AutoDelete",
                    detail: msg,
                    life: level === "info" ? 4000 : 10000,
                });
            }
        });
    },
});

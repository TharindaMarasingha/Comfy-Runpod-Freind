// Comfy-Runpod-Freind by Tharinda Marasingha (https://github.com/TharindaMarasingha)
import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

const CREDIT = "© Tharinda Marasingha";
const CREDIT_HEIGHT = 14;

// Shows RunPod auto-delete messages from the Python side as toasts,
// and draws a small, subtle credit in the bottom-right corner of the node.
app.registerExtension({
    name: "TharindaMarasingha.RunPodAutoDelete",
    beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "RunPodDeleteAfterUpload") return;

        const computeSize = nodeType.prototype.computeSize;
        nodeType.prototype.computeSize = function (...args) {
            const size = computeSize ? computeSize.apply(this, args) : [200, 100];
            size[1] += CREDIT_HEIGHT;
            return size;
        };

        const onDrawForeground = nodeType.prototype.onDrawForeground;
        nodeType.prototype.onDrawForeground = function (ctx) {
            onDrawForeground?.apply(this, arguments);
            if (this.flags?.collapsed) return;
            ctx.save();
            ctx.font = "italic 10px sans-serif";
            ctx.fillStyle = "rgba(170, 170, 170, 0.45)";
            ctx.textAlign = "right";
            ctx.textBaseline = "bottom";
            ctx.fillText(CREDIT, this.size[0] - 8, this.size[1] - 3);
            ctx.restore();
        };
    },
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

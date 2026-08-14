import express from "express";
import path from "path";
import { createServer as createViteServer } from "vite";
import dotenv from "dotenv";

dotenv.config();

const app = express();
const PORT = Number(process.env.PORT || 3000);
const CLOUD_URL = (process.env.JARVIS_CLOUD_URL || "").replace(/\/$/, "");
const CLOUD_SECRET = process.env.JARVIS_CLOUD_SECRET || "";
const DEVICE_ID = process.env.JARVIS_DEVICE_ID || "web-ui";

app.use(express.json({ limit: "1mb" }));

function cloudHeaders(extra: Record<string, string> = {}) {
  const headers: Record<string, string> = { "Content-Type": "application/json", "X-Device-ID": DEVICE_ID, ...extra };
  if (CLOUD_SECRET) headers.Authorization = `Bearer ${CLOUD_SECRET}`;
  return headers;
}

function cloudConfigured() { return Boolean(CLOUD_URL && CLOUD_SECRET); }

async function cloudFetch(pathname: string, init: RequestInit = {}) {
  if (!cloudConfigured()) throw new Error("Jarvis Cloud is not configured");
  return fetch(`${CLOUD_URL}${pathname}`, { ...init, headers: cloudHeaders((init.headers || {}) as Record<string, string>) });
}

app.get("/api/health", async (_req, res) => {
  if (!cloudConfigured()) return res.json({ status: "local", system: "JARVIS HUD", cloud: false });
  try {
    const response = await fetch(`${CLOUD_URL}/health`, { headers: cloudHeaders() });
    const data = await response.json();
    return res.status(response.status).json({ ...data, cloud: response.ok });
  } catch (error) {
    console.error("Cloud health error:", error);
    return res.status(503).json({ status: "offline", system: "Jarvis Cloud", cloud: false });
  }
});

app.post("/api/chat", async (req, res) => {
  try {
    const { message, history } = req.body || {};
    if (!message || typeof message !== "string") return res.status(400).json({ error: "Message is required" });
    if (!cloudConfigured()) return res.status(503).json({ error: "Jarvis Cloud is not configured", reply: "Cloud connection is not configured on this interface, sir.", source: "web-local" });
    const prompt = Array.isArray(history) && history.length ? `Recent conversation:\n${JSON.stringify(history.slice(-6))}\n\nCurrent request:\n${message}` : message;
    const response = await cloudFetch("/ask", { method: "POST", body: JSON.stringify({ message: prompt }) });
    const data = await response.json();
    return res.status(response.status).json({ reply: data.reply || "I'm here, boss.", mode: data.mode || "chat", session_id: data.session_id || null, device_id: DEVICE_ID, source: "jarvis-cloud" });
  } catch (error) {
    console.error("JARVIS Cloud chat error:", error);
    return res.status(503).json({ error: "Cloud unavailable", reply: "I can't reach the cloud brain right now, sir.", source: "web-cloud-error" });
  }
});

app.post("/api/instagram/brief", async (req, res) => {
  try {
    const request = typeof req.body?.request === "string" && req.body.request.trim() ? req.body.request.trim() : "Give me today's Instagram status, audience performance, and the content you plan to post today. Keep the Instagram account identity anonymous.";
    if (!cloudConfigured()) return res.status(503).json({ error: "Jarvis Cloud is not configured" });
    const response = await cloudFetch("/ask", { method: "POST", body: JSON.stringify({ message: request }) });
    const data = await response.json();
    return res.status(response.status).json({ reply: data.reply || "No Instagram briefing available.", mode: data.mode || "chat", source: "jarvis-cloud" });
  } catch (error) {
    console.error("Instagram brief error:", error);
    return res.status(503).json({ error: "Instagram briefing unavailable" });
  }
});

app.post("/api/device/heartbeat", async (_req, res) => {
  try {
    if (!cloudConfigured()) return res.status(503).json({ ok: false, error: "Cloud not configured" });
    const response = await cloudFetch("/device/heartbeat", { method: "POST", body: JSON.stringify({ device_id: DEVICE_ID, kind: "web" }) });
    return res.status(response.status).json(await response.json());
  } catch (error) {
    console.error("Heartbeat error:", error);
    return res.status(503).json({ ok: false });
  }
});

async function startServer() {
  if (process.env.NODE_ENV !== "production") {
    const vite = await createViteServer({ server: { middlewareMode: true }, appType: "spa" });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), "dist");
    app.use(express.static(distPath));
    app.get("*", (_req, res) => res.sendFile(path.join(distPath, "index.html")));
  }
  app.listen(PORT, "0.0.0.0", () => console.log(`JARVIS HUD running on http://0.0.0.0:${PORT}`));
}
startServer();

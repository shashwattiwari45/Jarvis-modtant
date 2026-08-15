import express from "express";
import path from "path";
import crypto from "crypto";
import { createServer as createViteServer } from "vite";
import dotenv from "dotenv";

dotenv.config();

const app = express();
const PORT = Number(process.env.PORT || 3000);
const CLOUD_URL = (process.env.JARVIS_CLOUD_URL || "").replace(/\/$/, "");
const CLOUD_SECRET = process.env.JARVIS_CLOUD_SECRET || "";
const DEVICE_ID = process.env.JARVIS_DEVICE_ID || "web-ui";
const OWNER_PASSWORD = process.env.JARVIS_OWNER_PASSWORD || "";
const AUTH_SECRET = process.env.JARVIS_AUTH_SECRET || "";
const OWNER_ID = "owner";
const AUTH_COOKIE = "jarvis_owner";
const AUTH_TTL_SECONDS = 7 * 24 * 60 * 60;

if (!OWNER_PASSWORD) throw new Error("JARVIS_OWNER_PASSWORD is required");
if (!AUTH_SECRET) throw new Error("JARVIS_AUTH_SECRET is required");

app.use(express.json({ limit: "1mb" }));

function cloudHeaders(extra: Record<string, string> = {}) {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "X-Device-ID": DEVICE_ID,
    "X-Owner-ID": OWNER_ID,
    ...extra,
  };
  if (CLOUD_SECRET) headers.Authorization = `Bearer ${CLOUD_SECRET}`;
  return headers;
}

function cloudConfigured() {
  return Boolean(CLOUD_URL && CLOUD_SECRET);
}

async function cloudFetch(pathname: string, init: RequestInit = {}) {
  if (!cloudConfigured()) throw new Error("Jarvis Cloud is not configured");
  return fetch(`${CLOUD_URL}${pathname}`, {
    ...init,
    headers: cloudHeaders((init.headers || {}) as Record<string, string>),
  });
}

function hash(value: string) {
  return crypto.createHash("sha256").update(value).digest("hex");
}

function signAuthToken(expiresAt: number) {
  const payload = `${OWNER_ID}:${expiresAt}`;
  const signature = crypto.createHmac("sha256", AUTH_SECRET).update(payload).digest("hex");
  return `${Buffer.from(payload).toString("base64url")}.${signature}`;
}

function isOwnerAuthenticated(req: express.Request) {
  const raw = req.headers.cookie || "";
  const match = raw.split(";").map((part) => part.trim()).find((part) => part.startsWith(`${AUTH_COOKIE}=`));
  if (!match) return false;
  const token = decodeURIComponent(match.slice(`${AUTH_COOKIE}=`.length));
  const [encodedPayload, signature] = token.split(".");
  if (!encodedPayload || !signature) return false;
  try {
    const payload = Buffer.from(encodedPayload, "base64url").toString("utf8");
    const [ownerId, expiryRaw] = payload.split(":");
    const expiry = Number(expiryRaw);
    if (ownerId !== OWNER_ID || !Number.isFinite(expiry) || expiry < Math.floor(Date.now() / 1000)) return false;
    const expected = crypto.createHmac("sha256", AUTH_SECRET).update(payload).digest("hex");
    return crypto.timingSafeEqual(Buffer.from(signature), Buffer.from(expected));
  } catch {
    return false;
  }
}

function requireOwner(req: express.Request, res: express.Response) {
  if (isOwnerAuthenticated(req)) return true;
  res.status(401).json({ error: "Owner authentication required", authenticated: false });
  return false;
}

function setOwnerCookie(res: express.Response) {
  const expiresAt = Math.floor(Date.now() / 1000) + AUTH_TTL_SECONDS;
  const token = signAuthToken(expiresAt);
  const secure = process.env.NODE_ENV === "production" ? "; Secure" : "";
  res.setHeader("Set-Cookie", `${AUTH_COOKIE}=${encodeURIComponent(token)}; Max-Age=${AUTH_TTL_SECONDS}; HttpOnly; SameSite=Strict; Path=/${secure}`);
}

app.get("/api/auth/me", (req, res) => {
  res.json({ authenticated: isOwnerAuthenticated(req) });
});

app.post("/api/auth/login", (req, res) => {
  const password = typeof req.body?.password === "string" ? req.body.password : "";
  const valid = crypto.timingSafeEqual(Buffer.from(hash(password)), Buffer.from(hash(OWNER_PASSWORD)));
  if (!valid) return res.status(401).json({ authenticated: false, error: "Access denied" });
  setOwnerCookie(res);
  return res.json({ authenticated: true });
});

app.post("/api/auth/logout", (_req, res) => {
  const secure = process.env.NODE_ENV === "production" ? "; Secure" : "";
  res.setHeader("Set-Cookie", `${AUTH_COOKIE}=; Max-Age=0; HttpOnly; SameSite=Strict; Path=/${secure}`);
  return res.json({ authenticated: false });
});

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
  if (!requireOwner(req, res)) return;
  try {
    const { message, history, session_id } = req.body || {};
    if (!message || typeof message !== "string") return res.status(400).json({ error: "Message is required" });
    if (!cloudConfigured()) {
      return res.status(503).json({
        error: "Jarvis Cloud is not configured",
        reply: "Cloud connection is not configured on this interface, sir.",
        source: "web-local",
      });
    }

    const prompt = Array.isArray(history) && history.length
      ? `Recent conversation:\n${JSON.stringify(history.slice(-12))}\n\nCurrent request:\n${message}`
      : message;

    const payload: Record<string, unknown> = { message: prompt };
    if (typeof session_id === "string" && session_id.trim()) payload.session_id = session_id;

    const response = await cloudFetch("/ask", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    return res.status(response.status).json({
      reply: data.reply || "I'm here, boss.",
      mode: data.mode || "chat",
      session_id: data.session_id || null,
      device_id: DEVICE_ID,
      source: "jarvis-cloud",
      model: data.model || null,
      web_search: Boolean(data.web_search),
      memory_saved: data.memory_saved || [],
    });
  } catch (error) {
    console.error("JARVIS Cloud chat error:", error);
    return res.status(503).json({
      error: "Cloud unavailable",
      reply: "I can't reach the cloud brain right now, sir.",
      source: "web-cloud-error",
    });
  }
});

app.post("/api/instagram/brief", async (req, res) => {
  if (!requireOwner(req, res)) return;
  try {
    const request = typeof req.body?.request === "string" && req.body.request.trim()
      ? req.body.request.trim()
      : "Give me today's Instagram status, audience performance, and the content you plan to post today. Keep the Instagram account identity anonymous and discuss these details only as a private owner briefing.";

    if (!cloudConfigured()) return res.status(503).json({ error: "Jarvis Cloud is not configured" });

    const response = await cloudFetch("/ask", {
      method: "POST",
      body: JSON.stringify({ message: request }),
    });
    const data = await response.json();
    return res.status(response.status).json({
      reply: data.reply || "No Instagram briefing available.",
      mode: data.mode || "chat",
      session_id: data.session_id || null,
      source: "jarvis-cloud",
      privacy: "private-owner-briefing",
    });
  } catch (error) {
    console.error("Instagram brief error:", error);
    return res.status(503).json({ error: "Instagram briefing unavailable" });
  }
});

app.post("/api/device/heartbeat", async (req, res) => {
  if (!requireOwner(req, res)) return;
  try {
    if (!cloudConfigured()) return res.status(503).json({ ok: false, error: "Cloud not configured" });
    const response = await cloudFetch("/device/heartbeat", {
      method: "POST",
      body: JSON.stringify({ device_id: DEVICE_ID, kind: "web" }),
    });
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

  app.listen(PORT, "0.0.0.0", () => {
    console.log(`JARVIS HUD running on http://0.0.0.0:${PORT}`);
    console.log(`Jarvis Cloud: ${cloudConfigured() ? CLOUD_URL : "NOT CONFIGURED"}`);
  });
}

startServer();

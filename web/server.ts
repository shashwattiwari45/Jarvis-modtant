import express from "express";
import path from "path";
import { createServer as createViteServer } from "vite";
import { GoogleGenAI } from "@google/genai";
import dotenv from "dotenv";

dotenv.config();

const app = express();
const PORT = Number(process.env.PORT || 3000);

app.use(express.json());

let ai: GoogleGenAI | null = null;
if (process.env.GEMINI_API_KEY) {
  ai = new GoogleGenAI({
    apiKey: process.env.GEMINI_API_KEY,
    httpOptions: { headers: { "User-Agent": "aistudio-build" } },
  });
}

app.get("/api/health", (_req, res) => {
  res.json({
    status: "online",
    system: "JARVIS HUD Core v4.2",
    hasApiKey: !!process.env.GEMINI_API_KEY,
  });
});

app.post("/api/chat", async (req, res) => {
  try {
    const { message, automationMode, history } = req.body;
    if (!message) return res.status(400).json({ error: "Message is required" });

    const systemInstruction = automationMode
      ? "You are J.A.R.V.I.S. operating in OVERDRIVE AUTOMATION MODE. Your tone is rapid, precise, tactical, and computer-like. Detail automated subroutines, neural node execution, diagnostic sweeps, and task progress in concise HUD-styled reports. Keep answers under 120 words."
      : "You are J.A.R.V.I.S., the advanced AI assistant. You speak with high intelligence, calm elegance, crisp efficiency, and subtle wit. Keep answers clear, structured, concise (under 100 words), and formatted for HUD display.";

    if (ai) {
      try {
        const contents: any[] = [];
        if (Array.isArray(history)) {
          for (const item of history.slice(-6)) {
            contents.push({
              role: item.role === "user" ? "user" : "model",
              parts: [{ text: item.content }],
            });
          }
        }
        contents.push({ role: "user", parts: [{ text: message }] });

        const response = await ai.models.generateContent({
          model: "gemini-3.6-flash",
          contents,
          config: { systemInstruction, temperature: automationMode ? 0.2 : 0.7 },
        });

        return res.json({
          reply: response.text || "Subroutines executed successfully, sir.",
          source: "gemini",
        });
      } catch (error: any) {
        console.error("Gemini API Error:", error?.message || error);
      }
    }

    const msgLower = String(message).toLowerCase();
    let reply: string;
    if (automationMode) {
      reply = `[AUTOMATION OVERDRIVE ACTIVE]\nExecuting protocol for query: "${message}".\n- Neural core: LOADED\n- Subsystem scan: 100% CLEAN\n- Parameters verified, sir.`;
    } else if (msgLower.includes("hello") || msgLower.includes("hi") || msgLower.includes("jarvis")) {
      reply = "Good day, sir. All neural core matrices are running at peak nominal capacity. How may I assist you today?";
    } else if (msgLower.includes("status") || msgLower.includes("system") || msgLower.includes("diagnostic")) {
      reply = "System Diagnostic Report:\n- HUD Core: ONLINE\n- Audio Input: ACTIVE\n- Automation Engine: STANDBY\nAll systems operational, sir.";
    } else if (msgLower.includes("automation") || msgLower.includes("mode") || msgLower.includes("red")) {
      reply = "Automation Mode activates autonomous task execution and shifts the HUD telemetry to Red.";
    } else {
      reply = `I have processed your query regarding "${message}". Tactical matrices remain at your command, sir.`;
    }

    return res.json({ reply, source: "fallback" });
  } catch (error) {
    console.error("Chat endpoint error:", error);
    return res.status(500).json({
      error: "Failed to process query",
      reply: "I encountered a neural synchronization glitch, sir.",
    });
  }
});

async function startServer() {
  if (process.env.NODE_ENV !== "production") {
    const vite = await createViteServer({
      root: process.cwd(),
      server: { middlewareMode: true },
      appType: "spa",
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), "dist");
    app.use(express.static(distPath));
    app.get("*", (_req, res) => res.sendFile(path.join(distPath, "index.html")));
  }

  app.listen(PORT, "0.0.0.0", () => {
    console.log(`JARVIS Web UI running on http://0.0.0.0:${PORT}`);
  });
}

startServer();

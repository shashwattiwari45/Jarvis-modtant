import express from "express";
import path from "path";
import { createServer as createViteServer } from "vite";
import { GoogleGenAI } from "@google/genai";
import dotenv from "dotenv";

dotenv.config();

const app = express();
const PORT = 3000;

app.use(express.json());

// Initialize Gemini Client safely
let ai: GoogleGenAI | null = null;
if (process.env.GEMINI_API_KEY) {
  ai = new GoogleGenAI({
    apiKey: process.env.GEMINI_API_KEY,
    httpOptions: {
      headers: {
        "User-Agent": "aistudio-build",
      },
    },
  });
}

// API Health
app.get("/api/health", (_req, res) => {
  res.json({
    status: "online",
    system: "JARVIS HUD Core v4.2",
    hasApiKey: !!process.env.GEMINI_API_KEY,
  });
});

// Chat API Route
app.post("/api/chat", async (req, res) => {
  try {
    const { message, automationMode, history } = req.body;

    if (!message) {
      return res.status(400).json({ error: "Message is required" });
    }

    // Default system prompt
    const systemInstruction = automationMode
      ? "You are J.A.R.V.I.S. operating in OVERDRIVE AUTOMATION MODE. Your tone is rapid, precise, tactical, and computer-like. Detail automated subroutines, neural node execution, diagnostic sweeps, and task progress in concise HUD-styled reports. Keep answers under 120 words."
      : "You are J.A.R.V.I.S., the advanced AI assistant. You speak with high intelligence, calm elegance, crisp efficiency, and subtle wit (like Tony Stark's assistant). Keep answers clear, structured, concise (under 100 words), and formatted for HUD display.";

    if (ai) {
      try {
        const contents = [];
        if (Array.isArray(history)) {
          for (const item of history.slice(-6)) {
            contents.push({
              role: item.role === "user" ? "user" : "model",
              parts: [{ text: item.content }],
            });
          }
        }
        contents.push({
          role: "user",
          parts: [{ text: message }],
        });

        const response = await ai.models.generateContent({
          model: "gemini-3.6-flash",
          contents,
          config: {
            systemInstruction,
            temperature: automationMode ? 0.2 : 0.7,
          },
        });

        const replyText = response.text || "Subroutines executed successfully, sir.";
        return res.json({ reply: replyText, source: "gemini" });
      } catch (geminiError: any) {
        console.error("Gemini API Error:", geminiError?.message || geminiError);
        // Fallback response on API error
      }
    }

    // Fallback JARVIS Intelligence response generator when key is unconfigured or errored
    const msgLower = message.toLowerCase();
    let reply = "";

    if (automationMode) {
      reply = `[AUTOMATION OVERDRIVE ACTIVE]\nExecuting protocol for query: "${message}".\n- Neural core: LOADED\n- Subsystem scan: 100% CLEAN\n- Task scheduled across 8 parallel worker threads. All parameters verified, sir.`;
    } else if (msgLower.includes("hello") || msgLower.includes("hi") || msgLower.includes("jarvis")) {
      reply = "Good day, sir. All neural core matrices are running at peak nominal capacity. How may I assist you today?";
    } else if (msgLower.includes("status") || msgLower.includes("system") || msgLower.includes("diagnostic")) {
      reply = "System Diagnostic Report:\n- WebGL Shader Core: 60 FPS\n- Thermal Levels: 34.2°C\n- Audio Input Buffer: Active\n- Automation Engine: Standby\nAll systems operational, sir.";
    } else if (msgLower.includes("automation") || msgLower.includes("mode") || msgLower.includes("red")) {
      reply = "Automation Mode empowers full-autonomous task execution. Toggling automation mode shifts core spectral telemetry to Red and activates background neural routines.";
    } else {
      reply = `I have processed your query regarding "${message}". Tactical matrices and core algorithms remain at your immediate command, sir.`;
    }

    return res.json({ reply, source: "fallback" });
  } catch (err: any) {
    console.error("Chat endpoint error:", err);
    res.status(500).json({ error: "Failed to process query", reply: "I encountered a neural synchronization glitch, sir." });
  }
});

async function startServer() {
  // Vite integration
  if (process.env.NODE_ENV !== "production") {
    const vite = await createViteServer({
      server: { middlewareMode: true },
      appType: "spa",
    });
    app.use(vite.middlewares);
  } else {
    const distPath = path.join(process.cwd(), "dist");
    app.use(express.static(distPath));
    app.get("*", (_req, res) => {
      res.sendFile(path.join(distPath, "index.html"));
    });
  }

  app.listen(PORT, "0.0.0.0", () => {
    console.log(`JARVIS Server running on http://0.0.0.0:${PORT}`);
  });
}

startServer();

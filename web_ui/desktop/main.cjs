const { app, BrowserWindow, shell } = require("electron");
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");
const http = require("http");

const DEV_MODE = process.argv.includes("--dev") || !app.isPackaged;
const PORT = Number(process.env.JARVIS_UI_PORT || 3000);
const repoRoot = process.env.JARVIS_PROJECT_ROOT || path.resolve(__dirname, "..", "..");
const webUiRoot = path.resolve(__dirname, "..");
const packagedRuntimeRoot = path.join(process.resourcesPath, "jarvis-runtime");
const runtimeRoot = app.isPackaged ? packagedRuntimeRoot : repoRoot;
const pythonCommand = process.env.JARVIS_PYTHON || "python";

let mainWindow = null;
let pythonProcess = null;
let uiProcess = null;
let quitting = false;

function log(prefix, data) {
  const text = String(data || "").trim();
  if (text) console.log(`[${prefix}] ${text}`);
}

function spawnProcess(command, args, options, label) {
  const child = spawn(command, args, {
    cwd: options.cwd,
    env: { ...process.env, ...(options.env || {}) },
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
  });

  child.stdout.on("data", (data) => log(label, data));
  child.stderr.on("data", (data) => log(`${label}:ERR`, data));
  child.on("error", (error) => console.error(`[${label}] failed:`, error));
  child.on("exit", (code, signal) => console.log(`[${label}] exited code=${code} signal=${signal || "none"}`));
  return child;
}

function startPythonBackend() {
  const pythonCwd = runtimeRoot;
  const args = ["-m", "jarvis.local_entrypoint"];
  pythonProcess = spawnProcess(pythonCommand, args, { cwd: pythonCwd }, "JARVIS-PYTHON");
}

function startWebServer() {
  if (DEV_MODE) {
    uiProcess = spawnProcess(process.platform === "win32" ? "npm.cmd" : "npm", ["run", "dev"], {
      cwd: webUiRoot,
      env: { PORT: String(PORT), NODE_ENV: "development" },
    }, "JARVIS-HUD");
  } else {
    const serverPath = path.join(webUiRoot, "dist", "server.cjs");
    if (!fs.existsSync(serverPath)) {
      throw new Error(`Built HUD server not found: ${serverPath}. Run npm run build first.`);
    }
    uiProcess = spawnProcess(process.execPath, [serverPath], {
      cwd: webUiRoot,
      env: { PORT: String(PORT), NODE_ENV: "production" },
    }, "JARVIS-HUD");
  }
}

function waitForHttp(url, timeoutMs = 20000) {
  const started = Date.now();
  return new Promise((resolve, reject) => {
    const attempt = () => {
      const request = http.get(url, (response) => {
        response.resume();
        if (response.statusCode && response.statusCode < 500) return resolve();
        retry();
      });
      request.on("error", retry);
      request.setTimeout(1500, () => {
        request.destroy();
        retry();
      });
    };
    const retry = () => {
      if (Date.now() - started >= timeoutMs) return reject(new Error(`JARVIS HUD did not start on ${url}`));
      setTimeout(attempt, 250);
    };
    attempt();
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1100,
    minHeight: 700,
    backgroundColor: "#000000",
    show: false,
    autoHideMenuBar: true,
    title: "JARVIS",
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("https://") || url.startsWith("http://")) {
      shell.openExternal(url);
    }
    return { action: "deny" };
  });

  mainWindow.webContents.on("will-navigate", (event, url) => {
    if (!url.startsWith(`http://127.0.0.1:${PORT}`) && !url.startsWith(`http://localhost:${PORT}`)) {
      event.preventDefault();
      if (url.startsWith("https://") || url.startsWith("http://")) shell.openExternal(url);
    }
  });

  mainWindow.once("ready-to-show", () => mainWindow.show());
  mainWindow.on("closed", () => { mainWindow = null; });
}

async function boot() {
  await app.whenReady();
  app.setAppUserModelId("com.jarvis.hud");

  // The Render cloud service is intentionally NOT owned by this process.
  // Closing/shutting down the desktop app therefore cannot stop cloud handling.
  startPythonBackend();
  startWebServer();

  await waitForHttp(`http://127.0.0.1:${PORT}`);
  createWindow();
  await mainWindow.loadURL(`http://127.0.0.1:${PORT}`);
}

function stopProcess(child) {
  if (!child || child.killed) return;
  try { child.kill(); } catch (_) {}
}

app.on("before-quit", () => {
  quitting = true;
  stopProcess(pythonProcess);
  stopProcess(uiProcess);
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("activate", () => {
  if (mainWindow === null && !quitting) createWindow();
});

boot().catch((error) => {
  console.error("[JARVIS DESKTOP] Startup failed:", error);
  stopProcess(pythonProcess);
  stopProcess(uiProcess);
  app.quit();
});

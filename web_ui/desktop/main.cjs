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

function attachProcessLogging(child, label) {
  child.stdout.on("data", (data) => log(label, data));
  child.stderr.on("data", (data) => log(`${label}:ERR`, data));
  child.on("error", (error) => console.error(`[${label}] failed:`, error));
  child.on("exit", (code, signal) => console.log(`[${label}] exited code=${code} signal=${signal || "none"}`));
}

function spawnProcess(command, args, options, label) {
  const spawnOptions = {
    cwd: options.cwd,
    env: { ...process.env, ...(options.env || {}) },
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
  };

  if (process.platform === "win32" && options.windowsShell) {
    // Electron can inherit an npm lifecycle PATH that does not resolve npm.cmd
    // when the command is passed as a quoted executable. Let cmd.exe resolve
    // npm from PATH instead, and only quote individual arguments when needed.
    const quoteArg = (value) => {
      const text = String(value);
      return /[\s&()^|<>]/.test(text) ? `"${text.replace(/"/g, '\\"')}"` : text;
    };
    const commandLine = [command, ...args].map(quoteArg).join(" ");
    const child = spawn(process.env.ComSpec || "cmd.exe", ["/d", "/s", "/c", commandLine], spawnOptions);
    attachProcessLogging(child, label);
    return child;
  }

  const child = spawn(command, args, spawnOptions);
  attachProcessLogging(child, label);
  return child;
}

function startPythonBackend() {
  pythonProcess = spawnProcess(
    pythonCommand,
    ["-m", "jarvis.local_entrypoint"],
    { cwd: runtimeRoot },
    "JARVIS-PYTHON",
  );
}

function startWebServer() {
  if (DEV_MODE) {
    uiProcess = spawnProcess(
      "npm",
      ["run", "dev"],
      {
        cwd: webUiRoot,
        env: { PORT: String(PORT), NODE_ENV: "development" },
        windowsShell: process.platform === "win32",
      },
      "JARVIS-HUD",
    );
    return;
  }

  const serverPath = path.join(webUiRoot, "dist", "server.cjs");
  if (!fs.existsSync(serverPath)) {
    throw new Error(`Built HUD server not found: ${serverPath}. Run npm run build first.`);
  }

  uiProcess = spawnProcess(
    process.execPath,
    [serverPath],
    {
      cwd: process.env.TEMP || process.env.TMP || process.resourcesPath,
      env: {
        PORT: String(PORT),
        NODE_ENV: "production",
        ELECTRON_RUN_AS_NODE: "1",
        JARVIS_WEB_ROOT: webUiRoot,
      },
    },
    "JARVIS-HUD",
  );
}

function waitForHttp(url, timeoutMs = 20000) {
  const started = Date.now();
  return new Promise((resolve, reject) => {
    const retry = () => {
      if (Date.now() - started >= timeoutMs) {
        reject(new Error(`JARVIS HUD did not start on ${url}`));
        return;
      }
      setTimeout(attempt, 250);
    };
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
    if (url.startsWith("https://") || url.startsWith("http://")) shell.openExternal(url);
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

  // Render/cloud is deliberately NOT owned by this process. Closing the
  // desktop app or shutting down Windows therefore does not stop cloud work.
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

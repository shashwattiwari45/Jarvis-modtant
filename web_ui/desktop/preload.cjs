const { contextBridge } = require("electron");

contextBridge.exposeInMainWorld("jarvisDesktop", Object.freeze({
  isDesktop: true,
  platform: process.platform,
  version: process.versions.electron,
}));

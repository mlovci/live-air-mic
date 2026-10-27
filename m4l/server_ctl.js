/**
 * LiveAirMic Max for Live Embedded Server & ADB Controller (Node for Max)
 * Automatically maintains the local Python audio bridge and USB ADB port-forwarding
 * tunnel, reconnecting seamlessly whenever a device is unplugged and re-plugged.
 */

const maxApi = require("max-api");
const { spawn, exec } = require("child_process");
const fs = require("fs");
const http = require("http");
const path = require("path");

const ROOT_DIR = path.resolve(__dirname, "..");
const BRIDGE_SCRIPT = path.join(ROOT_DIR, "server", "bridge.py");

const EXEC_ENV = Object.assign({}, process.env, {
  PATH: `/opt/homebrew/bin:/usr/local/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${process.env.PATH || ""}`,
  PYTHONUNBUFFERED: "1",
});

function resolveBinary(name, candidates) {
  for (const candidate of candidates) {
    try {
      if (fs.existsSync(candidate)) {
        return candidate;
      }
    } catch (e) {}
  }
  return name;
}

const PYTHON_BIN = resolveBinary("python3", [
  "/opt/homebrew/bin/python3",
  "/usr/local/homebrew/bin/python3",
  "/usr/local/bin/python3",
  "/usr/bin/python3",
]);

const ADB_BIN = resolveBinary("adb", [
  "/opt/homebrew/bin/adb",
  "/usr/local/homebrew/bin/adb",
  "/usr/local/bin/adb",
  path.join(process.env.HOME || "", "Library/Android/sdk/platform-tools/adb"),
]);

let bridgeProc = null;
let wantServerOn = true;
let wasClientConnected = false;

function getServerStatus() {
  return new Promise((resolve) => {
    const req = http.get("http://127.0.0.1:8765/api/status", { timeout: 600 }, (res) => {
      let body = "";
      res.on("data", (c) => (body += c));
      res.on("end", () => {
        try {
          resolve(res.statusCode === 200 ? JSON.parse(body) : null);
        } catch (e) {
          resolve(null);
        }
      });
    });
    req.on("error", () => resolve(null));
    req.on("timeout", () => {
      req.destroy();
      resolve(null);
    });
  });
}

function setupAdbTunnelOnly(cb) {
  exec(
    `"${ADB_BIN}" reverse tcp:8765 tcp:8765 && "${ADB_BIN}" reverse tcp:8766 tcp:8766`,
    { env: EXEC_ENV, timeout: 2500 },
    (err) => {
      if (cb) cb(!err);
    }
  );
}

function connectUsbPhoneAndOpenApp(forceRestart = false) {
  const apkPath = path.join(ROOT_DIR, "android-native", "LiveAirMic.apk");
  const startFlag = forceRestart ? "-S -W" : "";
  const cmd = `"${ADB_BIN}" reverse tcp:8765 tcp:8765 && "${ADB_BIN}" reverse tcp:8766 tcp:8766 && ("${ADB_BIN}" shell am start ${startFlag} -n com.liveairmic.pro/.MainActivity || (("${ADB_BIN}" install -r -g "${apkPath}" || ("${ADB_BIN}" uninstall com.liveairmic.pro && "${ADB_BIN}" install -g "${apkPath}")) && "${ADB_BIN}" shell am start -n com.liveairmic.pro/.MainActivity))`;
  exec(cmd, { env: EXEC_ENV, timeout: 10000 }, () => {});
}

async function startServer() {
  setupAdbTunnelOnly();
  const status = await getServerStatus();
  if (status) {
    maxApi.outlet("srv_state", 1);
    if (!status.connected_clients) {
      connectUsbPhoneAndOpenApp();
    }
    return;
  }

  maxApi.outlet("status_msg", "STARTING SERVER...");
  bridgeProc = spawn(PYTHON_BIN, [BRIDGE_SCRIPT, "--no-ssl"], {
    cwd: ROOT_DIR,
    env: EXEC_ENV,
    stdio: "ignore",
  });

  bridgeProc.on("exit", () => {
    bridgeProc = null;
    if (wantServerOn) {
      setTimeout(() => {
        if (wantServerOn) startServer();
      }, 1500);
    }
  });

  setTimeout(async () => {
    const st = await getServerStatus();
    maxApi.outlet("srv_state", st ? 1 : 0);
    if (st) {
      if (!st.connected_clients) {
        connectUsbPhoneAndOpenApp();
      }
    } else {
      maxApi.outlet("status_msg", "SERVER START FAILED");
    }
  }, 1200);
}

function stopServer() {
  if (bridgeProc) {
    try {
      bridgeProc.kill("SIGTERM");
    } catch (e) {}
    bridgeProc = null;
  }
  exec('pkill -f "server/bridge.py"', { env: EXEC_ENV }, () => {
    maxApi.outlet("srv_state", 0);
    maxApi.outlet("active_gate", 0);
    maxApi.outlet("status_msg", "SERVER STOPPED (Click SERVER OFF to start)");
  });
}

async function monitorServerAndUsbTunnel() {
  if (!wantServerOn) return;
  const st = await getServerStatus();
  if (!st) {
    if (!bridgeProc) {
      startServer();
    }
    return;
  }

  const hasClients = Number(st.connected_clients || 0) > 0;
  if (hasClients) {
    wasClientConnected = true;
  } else {
    // Whenever no client is connected (e.g. USB cable unplugged & re-plugged),
    // automatically re-establish `adb reverse` so the running phone app reconnects within 600ms.
    setupAdbTunnelOnly((tunnelOk) => {
      if (tunnelOk && wasClientConnected) {
        wasClientConnected = false;
      }
    });
  }
}

maxApi.addHandler("server_toggle", (state) => {
  if (Number(state) > 0) {
    wantServerOn = true;
    startServer();
  } else {
    wantServerOn = false;
    stopServer();
  }
});

maxApi.addHandler("usb_connect", () => {
  wantServerOn = true;
  http.get("http://127.0.0.1:8765/api/usb_connect", { timeout: 4000 }, () => {}).on("error", () => {});
  connectUsbPhoneAndOpenApp(true);
  startServer();
});

maxApi.addHandler("bang", () => {
  monitorServerAndUsbTunnel();
});

// Auto-verify / start server on load and keep server + USB ADB tunnel alive every 2.5s
startServer();
setInterval(monitorServerAndUsbTunnel, 2500);

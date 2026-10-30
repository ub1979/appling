const { app, BrowserWindow, shell } = require('electron');
const { spawn } = require('node:child_process');
const crypto = require('node:crypto');
const fs = require('node:fs');
const http = require('node:http');
const net = require('node:net');
const path = require('node:path');

let window;
let server;
let quitting = false;

if (process.env.APPLING_DESKTOP_TEST_DATA_DIR) {
  fs.mkdirSync(process.env.APPLING_DESKTOP_TEST_DATA_DIR, { recursive: true });
  app.setPath('userData', process.env.APPLING_DESKTOP_TEST_DATA_DIR);
}

const splash = `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><style>
body{margin:0;background:#10161c;color:#f3f7f7;font:16px system-ui,sans-serif;display:grid;place-items:center;height:100vh}
main{max-width:530px;padding:36px}b{font-size:40px;letter-spacing:-2px}p{line-height:1.5;color:#bed0d2}small{color:#93aeb2}
</style></head><body><main><b>Appling</b><p id="status">Preparing your workspace…</p><small>First launch downloads Python dependencies. Your projects stay in your own folders.</small></main></body></html>`;

function setStatus(message) {
  if (window && !window.isDestroyed() && !window.webContents.isLoading()) {
    window.webContents.executeJavaScript(
      `document.getElementById('status').textContent = ${JSON.stringify(message)}`
    ).catch(() => {});
  }
}

function run(program, args, cwd, log) {
  return new Promise((resolve, reject) => {
    const child = spawn(program, args, {
      cwd,
      env: { ...process.env, UV_NO_CONFIG: '1', UV_PROJECT_ENVIRONMENT: path.join(cwd, '.venv') },
      windowsHide: true,
    });
    child.stdout.on('data', chunk => log.write(chunk));
    child.stderr.on('data', chunk => log.write(chunk));
    child.on('error', reject);
    child.on('exit', code => code === 0 ? resolve() : reject(new Error(`${path.basename(program)} exited with code ${code}`)));
  });
}

function findPort() {
  return new Promise((resolve, reject) => {
    const listener = net.createServer();
    listener.once('error', reject);
    listener.listen(0, '127.0.0.1', () => {
      const port = listener.address().port;
      listener.close(() => resolve(port));
    });
  });
}

function waitForServer(port, token, child) {
  return new Promise((resolve, reject) => {
    const deadline = Date.now() + 60000;
    function probe() {
      if (child.exitCode !== null) return reject(new Error(`Appling exited with code ${child.exitCode}`));
      const request = http.get({ hostname: '127.0.0.1', port, path: '/api/projects',
        headers: { 'x-lyra-token': token }, timeout: 2000 }, response => {
        response.resume();
        if (response.statusCode === 200) resolve();
        else retry();
      });
      request.on('error', retry);
      request.on('timeout', () => request.destroy());
    }
    function retry() {
      if (Date.now() >= deadline) reject(new Error('Appling did not become ready within 60 seconds'));
      else setTimeout(probe, 500);
    }
    probe();
  });
}

async function start() {
  const data = app.getPath('userData');
  fs.mkdirSync(data, { recursive: true });
  const log = fs.createWriteStream(path.join(data, 'appling-startup.log'), { flags: 'a' });
  const bundled = app.isPackaged ? path.join(process.resourcesPath, 'runtime') : path.join(__dirname, 'build', 'runtime');
  const uv = path.join(app.isPackaged ? process.resourcesPath : path.join(__dirname, 'build'),
    'bin', process.platform === 'win32' ? 'uv.exe' : 'uv');
  const resources = app.isPackaged ? process.resourcesPath : path.join(__dirname, 'build');
  const commandPath = [path.join(resources, 'bin'),
    path.join(resources, 'node', process.platform === 'win32' ? '' : 'bin'),
    process.env.PATH || ''].join(path.delimiter);
  process.env.PATH = commandPath;
  process.env.UV_PYTHON_INSTALL_DIR = path.join(data, 'python');
  const runtime = path.join(data, `runtime-${app.getVersion()}`);
  const marker = path.join(runtime, '.appling-installed');

  try {
    if (!fs.existsSync(marker)) {
      setStatus('Copying Appling to your application data folder…');
      fs.rmSync(runtime, { recursive: true, force: true });
      fs.cpSync(bundled, runtime, { recursive: true });
      const support = path.join(runtime, '.appling-support');
      fs.mkdirSync(support, { recursive: true });
      setStatus('Preparing Node.js tools…');
      await run('tar', ['-xzf', path.join(resources, 'npm.tar.gz'), '-C', support], runtime, log);
      setStatus('Installing Python. This can take a few minutes on first launch…');
      await run(uv, ['python', 'install', '3.11', '--no-bin'], runtime, log);
      setStatus('Installing Appling dependencies…');
      await run(uv, ['sync', '--locked', '--no-dev', '--python', '3.11'], runtime, log);
      const hermes = path.join(runtime, '.venv', process.platform === 'win32' ? 'Scripts/hermes.exe' : 'bin/hermes');
      setStatus('Enabling the building tools…');
      await run(hermes, ['plugins', 'enable', 'ultimate-builder'], runtime, log);
      fs.writeFileSync(marker, app.getVersion());
    }

    process.env.APPLING_NPM_DIR = path.join(runtime, '.appling-support', 'npm');

    const python = path.join(runtime, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
    const port = await findPort();
    const token = crypto.randomBytes(32).toString('base64url');
    setStatus('Starting Appling…');
    server = spawn(python, ['-m', 'lyra_lite', '--no-open', '--port', String(port), '--token', token], {
      cwd: runtime,
      env: { ...process.env, PYTHONPATH: runtime },
      windowsHide: true,
      detached: process.platform !== 'win32',
    });
    server.stdout.on('data', chunk => log.write(chunk));
    server.stderr.on('data', chunk => log.write(chunk));
    server.on('error', error => log.write(`Server error: ${error.message}\n`));
    await waitForServer(port, token, server);
    const url = `http://127.0.0.1:${port}/`;
    window.webContents.setWindowOpenHandler(({ url: target }) => {
      if (target.startsWith(url)) return { action: 'allow' };
      if (/^https?:\/\//.test(target)) shell.openExternal(target);
      return { action: 'deny' };
    });
    window.webContents.on('will-navigate', (event, target) => {
      if (!target.startsWith(url)) {
        event.preventDefault();
        if (/^https?:\/\//.test(target)) shell.openExternal(target);
      }
    });
    await window.loadURL(url);
  } catch (error) {
    log.write(`Startup failed: ${error.stack || error}\n`);
    setStatus(`Could not start Appling: ${error.message}. See ${path.join(data, 'appling-startup.log')}`);
  }
}

app.whenReady().then(() => {
  if (!app.requestSingleInstanceLock()) { app.quit(); return; }
  window = new BrowserWindow({
    width: 1240, height: 850, minWidth: 850, minHeight: 600,
    backgroundColor: '#10161c',
    webPreferences: { nodeIntegration: false, contextIsolation: true, sandbox: true },
  });
  window.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(splash)}`);
  window.webContents.once('did-finish-load', () => void start());
  app.on('second-instance', () => { if (window) { window.show(); window.focus(); } });
  window.on('closed', () => app.quit());
});

app.on('before-quit', () => {
  if (quitting) return;
  quitting = true;
  if (server && server.exitCode === null) {
    if (process.platform === 'win32') spawn('taskkill', ['/PID', String(server.pid), '/T', '/F'], { windowsHide: true });
    else { try { process.kill(-server.pid, 'SIGTERM'); } catch { server.kill(); } }
  }
});

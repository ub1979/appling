// Exercise the runtime as it will be read from a native package. In particular,
// this catches missing source assets and platform-specific Python wheel issues.
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const appDir = path.resolve(__dirname, '..');
const platform = os.platform();
const arch = os.arch();
const resources = platform === 'darwin'
  ? path.join(appDir, 'release', `mac-${arch}`, 'Appling.app', 'Contents', 'Resources')
  : path.join(appDir, 'release', platform === 'win32' ? 'win-unpacked' : 'linux-unpacked', 'resources');
const runtime = path.join(resources, 'runtime');
const bin = path.join(resources, 'bin');
const node = path.join(resources, 'node', platform === 'win32' ? 'node.exe' : 'bin/node');
const npm = path.join(bin, platform === 'win32' ? 'npm.cmd' : 'npm');
const uv = path.join(bin, platform === 'win32' ? 'uv.exe' : 'uv');
const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'appling-smoke-'));
const venv = path.join(temp, 'venv');
const env = { ...process.env, UV_NO_CONFIG: '1', UV_PROJECT_ENVIRONMENT: venv,
  UV_PYTHON_INSTALL_DIR: path.join(temp, 'python'),
  HERMES_HOME: path.join(temp, 'hermes'),
  PYTHONPATH: runtime,
  APPLING_NPM_DIR: path.join(temp, 'npm'),
  PATH: [bin, path.dirname(node), process.env.PATH || ''].join(path.delimiter) };

function run(command, args, cwd = runtime) {
  const cmd = platform === 'win32' && command.endsWith('.cmd') ? 'cmd.exe' : command;
  const actualArgs = cmd === 'cmd.exe' ? ['/d', '/s', '/c', command, ...args] : args;
  execFileSync(cmd, actualArgs, { cwd, env, stdio: 'inherit', timeout: 15 * 60 * 1000 });
}

try {
  if (!fs.existsSync(path.join(runtime, 'lyra_lite', 'ui', 'dist', 'index.html'))) {
    throw new Error('Appling UI missing from package');
  }
  run(uv, ['--version']);
  run(node, ['--version']);
  run('tar', ['-xzf', path.join(resources, 'npm.tar.gz'), '-C', temp]);
  run(npm, ['--version']);
  run(uv, ['python', 'install', '3.11', '--no-bin']);
  run(uv, ['sync', '--locked', '--no-dev', '--python', '3.11']);
  const scripts = path.join(venv, platform === 'win32' ? 'Scripts' : 'bin');
  run(path.join(scripts, platform === 'win32' ? 'hermes.exe' : 'hermes'),
    ['plugins', 'enable', 'ultimate-builder']);
  run(path.join(scripts, platform === 'win32' ? 'python.exe' : 'python'), ['-c',
    'from fastapi.testclient import TestClient; from lyra_lite.server import create_app; '
    + 'c=TestClient(create_app(token="smoke-token")); '
    + 'r=c.get("/api/projects", headers={"x-lyra-token":"smoke-token", "host":"127.0.0.1"}); '
    + 'assert r.status_code == 200, r.text; '
    + 'assert "projects" in r.json(); '
    + 'assert c.get("/", headers={"host":"127.0.0.1"}).status_code == 200']);
  console.log('Packaged Appling runtime smoke test passed');
} finally {
  fs.rmSync(temp, { recursive: true, force: true });
}

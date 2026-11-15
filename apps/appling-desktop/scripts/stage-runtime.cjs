// Stage the exact checkout being packaged. Keep the source tree intact because
// Hermes loads skills, plugins and templates from paths relative to its repo.
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const appDir = path.resolve(__dirname, '..');
const repo = path.resolve(appDir, '../..');
const target = path.join(appDir, 'build', 'runtime');
const bin = path.join(appDir, 'build', 'bin');
const nodeTarget = path.join(appDir, 'build', 'node');
const npmTarget = path.join(appDir, 'build', 'npm');
const npmArchive = path.join(appDir, 'build', 'npm.tar.gz');
fs.rmSync(target, { recursive: true, force: true });
fs.rmSync(bin, { recursive: true, force: true });
fs.rmSync(nodeTarget, { recursive: true, force: true });
fs.rmSync(npmTarget, { recursive: true, force: true });
fs.rmSync(npmArchive, { force: true });
fs.mkdirSync(target, { recursive: true });
fs.mkdirSync(bin, { recursive: true });

// Package only Appling and its local asset helpers, never the Hermes runtime.
const excluded = new Set(['coordinator.py', 'delegation.py', 'recall_tool.py', 'hermes.py']);
function copyTree(source, destination) {
  if (!fs.existsSync(source)) return;
  for (const entry of fs.readdirSync(source, { withFileTypes: true })) {
    if (['node_modules', '__pycache__', 'ui', '.venv'].includes(entry.name) || excluded.has(entry.name)) continue;
    const from = path.join(source, entry.name);
    const to = path.join(destination, entry.name);
    if (entry.isDirectory()) copyTree(from, to);
    else if (entry.isFile()) {
      fs.mkdirSync(path.dirname(to), { recursive: true });
      fs.copyFileSync(from, to);
    }
  }
}
copyTree(path.join(repo, 'lyra_lite'), path.join(target, 'lyra_lite'));
for (const relative of [
  'plugins/ultimate-builder/skills/ultimate-app-builder/references/workflows/web-cinematic/scripts',
  'plugins/ultimate-builder/skills/ultimate-app-builder/references/workflows/deck-builder/scripts',
  'web/public/skill-avatars',
]) copyTree(path.join(repo, relative), path.join(target, relative));
for (const name of ['pyproject.toml', 'uv.lock']) {
  fs.copyFileSync(path.join(repo, 'apps/appling-runtime', name), path.join(target, name));
}
for (const name of ['LICENSE', 'NOTICE']) {
  if (fs.existsSync(path.join(repo, name))) fs.copyFileSync(path.join(repo, name), path.join(target, name));
}
const codexPath = require('./codex-binary.cjs').resolveCodex();
const codexName = os.platform() === 'win32' ? 'codex.exe' : 'codex';
fs.copyFileSync(fs.realpathSync(codexPath), path.join(bin, codexName));
fs.chmodSync(path.join(bin, codexName), 0o755);
execFileSync(path.join(bin, codexName), ['--version'], { stdio: 'ignore' });
// The distributed Codex binary's Apache license must accompany the package.
for (const name of ['CODEX-LICENSE', 'CODEX-NOTICE']) fs.copyFileSync(path.join(repo, 'apps/appling-runtime', name), path.join(target, name));

const browserSource = path.join(repo, 'apps/appling-browser');
if (!fs.existsSync(path.join(browserSource, 'node_modules/@playwright/cli/playwright-cli.js'))) {
  throw new Error('Install browser tools first: npm --prefix apps/appling-browser ci');
}
fs.cpSync(browserSource, path.join(target, 'apps/appling-browser'), { recursive: true, dereference: true });

const ui = path.join(repo, 'lyra_lite', 'ui', 'dist');
if (!fs.existsSync(path.join(ui, 'index.html'))) {
  throw new Error('Build the Appling UI first: cd lyra_lite/ui && npm ci && npm run build');
}
fs.cpSync(ui, path.join(target, 'lyra_lite', 'ui', 'dist'), { recursive: true });

const uvName = os.platform() === 'win32' ? 'uv.exe' : 'uv';
const uvPath = process.env.APPLING_UV_PATH || execFileSync(
  os.platform() === 'win32' ? 'where' : 'which', ['uv'], { encoding: 'utf8' }
).trim().split(/\r?\n/)[0];
fs.copyFileSync(uvPath, path.join(bin, uvName));
fs.chmodSync(path.join(bin, uvName), 0o755);

// Codex and the apps it builds invoke node/npm. Carry a portable Node binary.
// A Homebrew node executable is a tiny shim linked to libnode.dylib, so copy
// that library too when present; never copy an entire /usr/local prefix.
const nodeRoot = path.dirname(path.dirname(fs.realpathSync(process.execPath)));
const nodeBinDir = path.join(nodeTarget, os.platform() === 'win32' ? '' : 'bin');
fs.mkdirSync(nodeBinDir, { recursive: true });
const stagedNode = path.join(nodeBinDir, os.platform() === 'win32' ? 'node.exe' : 'node');
fs.copyFileSync(process.execPath, stagedNode);
fs.chmodSync(stagedNode, 0o755);
const libDir = path.join(nodeRoot, 'lib');
if (fs.existsSync(libDir)) {
  for (const name of fs.readdirSync(libDir).filter(name => /^libnode\./.test(name))) {
    const destination = path.join(nodeTarget, 'lib', name);
    fs.mkdirSync(path.dirname(destination), { recursive: true });
    fs.copyFileSync(path.join(libDir, name), destination);
  }
}
execFileSync(stagedNode, ['--version'], { stdio: 'ignore' });

const npmFromScript = process.env.npm_execpath
  ? path.dirname(path.dirname(process.env.npm_execpath)) : null;
let globalNpm = null;
if (!npmFromScript || !fs.existsSync(path.join(npmFromScript, 'bin', 'npm-cli.js'))) {
  const rootArgs = os.platform() === 'win32'
    ? ['C:/Windows/System32/cmd.exe', ['/d', '/s', '/c', 'npm.cmd', 'root', '-g']]
    : ['npm', ['root', '-g']];
  globalNpm = execFileSync(rootArgs[0], rootArgs[1], { encoding: 'utf8' }).trim();
}
const npmSource = [npmFromScript, globalNpm && path.join(globalNpm, 'npm'),
  path.join(nodeRoot, 'lib/node_modules/npm'), path.join(nodeRoot, 'node_modules/npm')]
  .filter(Boolean)
  .find(candidate => fs.existsSync(path.join(candidate, 'bin', 'npm-cli.js')));
if (!npmSource) throw new Error('Could not locate npm CLI to bundle');
fs.cpSync(npmSource, npmTarget, { recursive: true });
execFileSync('tar', ['-czf', npmArchive, '-C', path.join(appDir, 'build'), 'npm']);
fs.rmSync(npmTarget, { recursive: true, force: true });
if (os.platform() === 'win32') {
  for (const command of ['npm', 'npx']) {
    fs.writeFileSync(path.join(bin, `${command}.cmd`),
      `@echo off\r\n"%~dp0..\\node\\node.exe" "%APPLING_NPM_DIR%\\bin\\${command}-cli.js" %*\r\n`);
  }
} else {
  for (const command of ['npm', 'npx']) {
    const shim = path.join(bin, command);
    fs.writeFileSync(shim,
      `#!/bin/sh\nexec "$(dirname "$0")/../node/bin/node" "$APPLING_NPM_DIR/bin/${command}-cli.js" "$@"\n`);
    fs.chmodSync(shim, 0o755);
  }
}
console.log(`Staged Codex-only Appling runtime, UI, Codex, uv, Node and npm`);

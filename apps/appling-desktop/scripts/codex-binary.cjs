// Resolve an official standalone or npm Codex installation to its native binary.
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');

function isNative(file) {
  const fd = fs.openSync(file, 'r');
  const bytes = Buffer.alloc(4);
  try { fs.readSync(fd, bytes, 0, 4, 0); } finally { fs.closeSync(fd); }
  return bytes.subarray(0, 2).toString() === 'MZ' || bytes.equals(Buffer.from([0x7f, 0x45, 0x4c, 0x46]))
    || ['cffaedfe', 'feedfacf', 'cafebabe'].includes(bytes.toString('hex'));
}
function findNative(root, depth = 0) {
  if (depth > 8 || !fs.existsSync(root)) return null;
  for (const entry of fs.readdirSync(root, { withFileTypes: true })) {
    const file = path.join(root, entry.name);
    if (entry.isFile() && /^(codex|codex.exe)$/.test(entry.name) && isNative(file)) return file;
    if (entry.isDirectory()) {
      const found = findNative(file, depth + 1);
      if (found) return found;
    }
  }
  return null;
}
function resolveCodex() {
  const candidate = process.env.APPLING_CODEX_PATH || execFileSync(
    process.platform === 'win32' ? 'where' : 'which', ['codex'], { encoding: 'utf8' }
  ).trim().split(/\r?\n/)[0];
  const real = fs.realpathSync(candidate);
  if (isNative(real)) return real;
  const npmRoot = execFileSync(process.platform === 'win32' ? 'npm.cmd' : 'npm', ['root', '-g'], {
    encoding: 'utf8', shell: process.platform === 'win32',
  }).trim();
  const scope = path.join(npmRoot, '@openai');
  const roots = [path.dirname(path.dirname(real)),
    ...(fs.existsSync(scope) ? fs.readdirSync(scope).filter(name => name.startsWith('codex')).map(name => path.join(scope, name)) : [])];
  for (const root of roots) {
    const found = findNative(root);
    if (found) return found;
  }
  throw new Error('Codex native binary not found. Set APPLING_CODEX_PATH to the official native executable.');
}
module.exports = { resolveCodex, isNative };

// Build outside the repository's npm workspace so electron-builder only sees
// this launcher's zero production dependencies, not the Hermes root package.
const { execFileSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const appDir = path.resolve(__dirname, '..');
const target = process.argv[2];
if (!['dir', 'mac', 'win', 'linux'].includes(target)) throw new Error('Expected dir, mac, win or linux');
execFileSync(process.execPath, [path.join(__dirname, 'stage-runtime.cjs')], { stdio: 'inherit', cwd: appDir });

const isolated = fs.mkdtempSync(path.join(os.tmpdir(), 'appling-package-'));
try {
  const pkg = JSON.parse(fs.readFileSync(path.join(appDir, 'package.json'), 'utf8'));
  pkg.build.directories.output = path.join(appDir, 'release');
  fs.writeFileSync(path.join(isolated, 'package.json'), JSON.stringify(pkg, null, 2));
  for (const name of ['main.cjs']) fs.copyFileSync(path.join(appDir, name), path.join(isolated, name));
  fs.cpSync(path.join(appDir, 'icons'), path.join(isolated, 'icons'), { recursive: true });
  fs.cpSync(path.join(appDir, 'build'), path.join(isolated, 'build'), { recursive: true });
  const builder = path.join(appDir, 'node_modules', 'electron-builder', 'cli.js');
  const args = [builder, '--projectDir', isolated];
  if (target !== 'dir') args.push(`--${target}`);
  else args.push('--dir');
  execFileSync(process.execPath, args, { stdio: 'inherit', cwd: isolated, env: process.env });
} finally {
  fs.rmSync(isolated, { recursive: true, force: true });
}

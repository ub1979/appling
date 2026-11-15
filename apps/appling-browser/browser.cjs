// Run the official CLI in one Appling-owned session. No shared login profile.
const { spawnSync } = require('node:child_process');
const path = require('node:path');
const args = process.argv.slice(2);
if (!process.env.APPLING_BROWSER_CACHE || !process.env.APPLING_BROWSER_SESSION) {
  throw new Error('Run this browser command from an Appling Codex session.');
}
if (args[0] === 'open' && !args.some(arg => arg.startsWith('--config'))) {
  args.push('--config', process.env.APPLING_BROWSER_CONFIG);
}
const child = spawnSync(process.execPath, [path.join(__dirname, 'node_modules/@playwright/cli/playwright-cli.js'), ...args], {
  stdio: 'inherit',
  env: { ...process.env, XDG_CACHE_HOME: process.env.APPLING_BROWSER_CACHE,
    PLAYWRIGHT_CLI_SESSION: process.env.APPLING_BROWSER_SESSION,
    PLAYWRIGHT_MCP_OUTPUT_DIR: process.env.APPLING_BROWSER_OUTPUT },
});
if (child.error) throw child.error;
process.exitCode = child.status ?? 1;

#!/usr/bin/env node
// Lyra site check: open a built website in a real browser the way a visitor
// would (desktop + phone), scroll it top to bottom, and save what it saw.
//
//   node site-check.mjs [dist|index.html|http://url] [--compare reference.html]
//                       [--out .sdlc/qa/site-check] [--steps 10]
//
// It reports console/page errors, failed requests, sideways overflow, text
// left faint after scrolling past it, and broken reduced-motion. It also writes
// screenshots plus one contact sheet per screen size (`sheet-desktop.png`,
// `sheet-phone.png`). With --compare, each row shows the build next to the
// reference design at the same scroll point, so effects can be compared by eye.
//
// Exit codes: 0 = no problems found, 1 = problems found, 3 = BLOCKED (no browser).
// The browser is the installed Google Chrome (or Edge, or Playwright's
// Chromium); `playwright-core` is fetched once into a shared cache, never into
// the project.

import { createServer } from 'node:http';
import { createRequire } from 'node:module';
import { execSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const args = process.argv.slice(2);
const opt = (name, fallback) => {
  const i = args.indexOf(name);
  if (i < 0) return fallback;
  const v = args[i + 1];
  args.splice(i, 2);
  return v;
};
const out = path.resolve(opt('--out', '.sdlc/qa/site-check'));
const compare = opt('--compare', null);
const steps = Math.max(4, Math.min(24, Number(opt('--steps', 10)) || 10));
let target = args[0] || (fs.existsSync('dist/index.html') ? 'dist' : 'index.html');

const VIEWPORTS = [
  { name: 'desktop', width: 1440, height: 900, mobile: false },
  { name: 'phone', width: 390, height: 844, mobile: true },
];

function blocked(msg) {
  console.log(`BLOCKED: ${msg}`);
  fs.mkdirSync(out, { recursive: true });
  fs.writeFileSync(path.join(out, 'report.md'), `# Site check\n\n**BLOCKED** — ${msg}\n`);
  process.exit(3);
}

function loadPlaywright() {
  const home = process.env.HERMES_HOME || path.join(os.homedir(), '.hermes');
  const cache = path.join(home, 'cache', 'site-check');
  const pkg = path.join(cache, 'package.json');
  const req = createRequire(pkg);
  try { return req('playwright-core'); } catch {}
  try {
    fs.mkdirSync(cache, { recursive: true });
    if (!fs.existsSync(pkg)) fs.writeFileSync(pkg, '{"name":"lyra-site-check","private":true}');
    console.log('Installing playwright-core into', cache, '(one time)…');
    execSync('npm i --no-audit --no-fund playwright-core@1', { cwd: cache, stdio: 'inherit' });
    return req('playwright-core');
  } catch (e) {
    blocked(`could not install playwright-core (${e.message.split('\n')[0]}). Check the internet connection and that npm works.`);
  }
}

async function launch(chromium) {
  for (const channel of ['chrome', 'msedge', undefined]) {
    try { return await chromium.launch({ headless: true, ...(channel ? { channel } : {}) }); } catch {}
  }
  blocked('no browser found. Install Google Chrome (or run `npx playwright install chromium`) and run the check again.');
}

const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css',
  '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.avif': 'image/avif', '.gif': 'image/gif', '.woff2': 'font/woff2',
  '.woff': 'font/woff', '.ttf': 'font/ttf', '.mp4': 'video/mp4', '.webm': 'video/webm', '.glb': 'model/gltf-binary',
  '.ico': 'image/x-icon', '.txt': 'text/plain' };

// Serve a folder so module scripts and absolute /assets paths work like a host.
function serve(dir) {
  return new Promise((resolve) => {
    const server = createServer((req, res) => {
      let rel = decodeURIComponent(new URL(req.url, 'http://x').pathname);
      let file = path.join(dir, rel);
      if (!file.startsWith(dir)) { res.writeHead(403).end(); return; }
      if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, 'index.html');
      if (!fs.existsSync(file)) { res.writeHead(404).end('not found'); return; }
      res.writeHead(200, { 'content-type': TYPES[path.extname(file).toLowerCase()] || 'application/octet-stream' });
      fs.createReadStream(file).pipe(res);
    });
    server.listen(0, '127.0.0.1', () => resolve(server));
  });
}

async function urlFor(spec, servers) {
  if (/^https?:\/\//.test(spec)) return spec;
  const abs = path.resolve(spec);
  if (!fs.existsSync(abs)) blocked(`nothing to open at ${spec}. Run the build first (npm run build).`);
  const dir = fs.statSync(abs).isDirectory() ? abs : path.dirname(abs);
  const page = fs.statSync(abs).isDirectory() ? '' : path.basename(abs);
  const server = await serve(dir);
  servers.push(server);
  return `http://127.0.0.1:${server.address().port}/${page}`;
}

// In-page probes ------------------------------------------------------------

function probeOverflow() {
  const vw = document.documentElement.clientWidth;
  const sideways = document.documentElement.scrollWidth > vw + 1;
  const clipped = (el) => {
    for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
      const s = getComputedStyle(p);
      if (/(hidden|clip|auto|scroll)/.test(s.overflowX)) return true;
    }
    return false;
  };
  const wide = [];
  if (sideways) {
    for (const el of document.body.querySelectorAll('*')) {
      const r = el.getBoundingClientRect();
      if (r.width && (r.right > vw + 1 || r.left < -1) && !clipped(el)) {
        wide.push(`${el.tagName.toLowerCase()}${el.id ? '#' + el.id : ''}${el.classList.length ? '.' + [...el.classList].slice(0, 2).join('.') : ''} (${Math.round(r.left)}→${Math.round(r.right)}px)`);
        if (wide.length >= 6) break;
      }
    }
  }
  return { sideways, pageWidth: document.documentElement.scrollWidth, vw, wide };
}

// Text in the middle band of the screen with its effective opacity, so the
// walk can tell "revealed later" from "never revealed". Text stacked under
// other visible text (story beats that take turns) is marked as covered.
function probeText() {
  const vh = innerHeight;
  const rows = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const seen = new Set();
  const effective = (el) => {
    let opacity = 1;
    for (let p = el; p; p = p.parentElement) {
      const s = getComputedStyle(p);
      if (s.visibility === 'hidden' || s.display === 'none') return 0;
      opacity *= Number(s.opacity);
    }
    const alpha = /rgba?\(([^)]+)\)/.exec(getComputedStyle(el).color)?.[1].split(/[ ,/]+/).filter(Boolean)[3];
    return opacity * (alpha === undefined ? 1 : Number(alpha));
  };
  while (walker.nextNode()) {
    const node = walker.currentNode;
    const text = node.textContent.trim();
    if (text.length < 3) continue;
    const el = node.parentElement;
    if (!el || seen.has(el)) continue;
    seen.add(el);
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height || r.bottom < 0 || r.top > vh) continue;
    // Giant background wordmarks and aria-hidden ornaments are meant to be faint.
    if (el.closest('[aria-hidden="true"]') || parseFloat(getComputedStyle(el).fontSize) >= 120) continue;
    const mid = r.top >= vh * 0.2 && r.bottom <= vh * 0.8;
    if (!el.dataset.scId) el.dataset.scId = String(Math.random()).slice(2, 10);
    rows.push({ id: el.dataset.scId, text: text.slice(0, 60), eff: Math.round(effective(el) * 100) / 100, r, mid });
  }
  const visible = rows.filter((x) => x.eff >= 0.4);
  return rows.map(({ id, text, eff, r, mid }) => ({
    id, text, eff, mid,
    covered: eff < 0.4 && visible.some((v) => v.r.left < r.right && v.r.right > r.left && v.r.top < r.bottom && v.r.bottom > r.top),
  }));
}

function faintTexts(samples) {
  // Flag text that was faint and uncovered mid-screen, and never readable
  // anywhere on screen in any step.
  const best = new Map();
  for (const s of samples) {
    const cur = best.get(s.id) || { ...s, max: 0, flagged: false };
    cur.max = Math.max(cur.max, s.eff);
    if (s.mid && s.eff < 0.4 && !s.covered && !cur.flagged) Object.assign(cur, { flagged: true, step: s.step, eff: s.eff });
    best.set(s.id, cur);
  }
  return [...best.values()].filter((x) => x.flagged && x.max < 0.4);
}

// Scrolling -----------------------------------------------------------------

const maxScroll = (page) => page.evaluate(() => Math.max(0, document.documentElement.scrollHeight - innerHeight));
const scrollY = (page) => page.evaluate(() => Math.round(scrollY));

async function settle(page, ms = 450) { await page.waitForTimeout(ms); }

// Wheel like a visitor so smooth-scroll libraries and pinned sections react
// for real; fall back to scrollTo if wheel input is ignored.
async function scrollToY(page, y, mobile) {
  for (let i = 0; i < 40; i++) {
    const now = await scrollY(page);
    const gap = y - now;
    if (Math.abs(gap) < 30) break;
    if (mobile) await page.evaluate((d) => window.scrollBy(0, d), Math.sign(gap) * Math.min(Math.abs(gap), 700));
    else await page.mouse.wheel(0, Math.sign(gap) * Math.min(Math.abs(gap), 600));
    await settle(page, 120);
    if (i > 6 && Math.abs((await scrollY(page)) - now) < 2) {
      await page.evaluate((t) => window.scrollTo(0, t), y);
      break;
    }
  }
  await settle(page);
}

async function walk(browser, url, vp, prefix, findings, record) {
  const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height },
    deviceScaleFactor: 1, isMobile: vp.mobile, hasTouch: vp.mobile });
  const page = await ctx.newPage();
  const errors = [];
  const failed = [];
  if (record) {
    page.on('console', (m) => { if (m.type() === 'error' && !/status of 404/.test(m.text())) errors.push(m.text().slice(0, 200)); });
    page.on('pageerror', (e) => errors.push(String(e.message || e).slice(0, 200)));
    const icon = (u) => /favicon\.ico$/.test(u);
    page.on('requestfailed', (r) => icon(r.url()) || failed.push(`${r.url().slice(0, 120)} (${r.failure()?.errorText || 'failed'})`));
    page.on('response', (r) => { if (r.status() >= 400 && !icon(r.url())) failed.push(`${r.url().slice(0, 120)} (HTTP ${r.status()})`); });
  }
  await page.goto(url, { waitUntil: 'load', timeout: 30000 });
  await page.waitForLoadState('networkidle', { timeout: 8000 }).catch(() => {});
  await settle(page, 900);
  const shots = [];
  const faintSeen = [];
  let overflow = await page.evaluate(probeOverflow);
  for (let i = 0; i < steps; i++) {
    const total = await maxScroll(page); // pins add height as they set up
    const y = Math.round((total * i) / (steps - 1));
    await scrollToY(page, y, vp.mobile);
    const file = path.join(out, `${prefix}-${vp.name}-${String(i).padStart(2, '0')}.png`);
    await page.screenshot({ path: file });
    shots.push(file);
    if (record) {
      const o = await page.evaluate(probeOverflow);
      if (o.sideways && !overflow.sideways) overflow = o;
      // Only judge text once the visitor has had time to scroll past it.
      for (const f of await page.evaluate(probeText)) faintSeen.push({ ...f, step: i });
    }
  }
  if (record) {
    const tag = `[${vp.name}]`;
    for (const e of [...new Set(errors)]) findings.push(`${tag} Console/page error: ${e}`);
    for (const f of [...new Set(failed)]) findings.push(`${tag} Failed request: ${f}`);
    if (overflow.sideways) findings.push(`${tag} Page scrolls sideways: ${overflow.pageWidth}px wide on a ${overflow.vw}px screen. Widest: ${overflow.wide.join('; ') || 'unknown'}`);
    for (const f of faintTexts(faintSeen).slice(0, 6)) {
      findings.push(`${tag} Text never became readable (opacity ${f.eff} at step ${f.step}, mid-screen): "${f.text}" — a reveal that never finished?`);
    }
  }
  await ctx.close();
  return shots;
}

async function reducedMotion(browser, url, findings) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'reduce' });
  const page = await ctx.newPage();
  await page.goto(url, { waitUntil: 'load', timeout: 30000 });
  await page.waitForLoadState('networkidle', { timeout: 8000 }).catch(() => {});
  await settle(page, 600);
  const total = await maxScroll(page);
  const samples = [];
  for (let i = 1; i < 12; i++) {
    await page.evaluate((t) => window.scrollTo(0, t), Math.round((total * i) / 12));
    await settle(page, 800);
    for (const f of await page.evaluate(probeText)) samples.push({ ...f, step: i });
  }
  const faint = faintTexts(samples);
  const file = path.join(out, 'reduced-motion.png');
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: file, fullPage: total < 20000 });
  if (faint.length) findings.push(`[reduced motion] Text stays hidden for visitors who turn motion off: "${faint[0].text}"`);
  await ctx.close();
  return file;
}

async function contactSheet(browser, vp, built, reference) {
  const cols = reference ? 2 : (vp.mobile ? 5 : 3);
  const w = vp.mobile ? 195 : 480;
  const h = Math.round((w * vp.height) / vp.width);
  const cell = (f, label) => `<figure><img src="data:image/png;base64,${fs.readFileSync(f).toString('base64')}"><figcaption>${label}</figcaption></figure>`;
  let cells = '';
  built.forEach((f, i) => {
    cells += cell(f, `${reference ? 'Build · ' : ''}step ${i}`);
    if (reference && reference[i]) cells += cell(reference[i], `Reference · step ${i}`);
  });
  const html = `<style>body{margin:0;padding:12px;background:#111;color:#ddd;font:12px system-ui}
    main{display:grid;grid-template-columns:repeat(${cols},${w}px);gap:10px}
    figure{margin:0}img{width:${w}px;height:${h}px;object-fit:cover;object-position:top;display:block;border:1px solid #333}
    figcaption{padding:3px 0}</style><main>${cells}</main>`;
  const page = await browser.newPage({ viewport: { width: cols * (w + 10) + 24, height: 600 } });
  await page.setContent(html);
  const file = path.join(out, `sheet-${vp.name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  await page.close();
  return file;
}

// Main ----------------------------------------------------------------------

const { chromium } = loadPlaywright();
fs.rmSync(out, { recursive: true, force: true });
fs.mkdirSync(out, { recursive: true });
const browser = await launch(chromium);
const servers = [];
const findings = [];
const sheets = [];
try {
  const url = await urlFor(target, servers);
  const refUrl = compare ? await urlFor(compare, servers) : null;
  for (const vp of VIEWPORTS) {
    const built = await walk(browser, url, vp, 'build', findings, true);
    const ref = refUrl ? await walk(browser, refUrl, vp, 'reference', [], false) : null;
    sheets.push(await contactSheet(browser, vp, built, ref));
  }
  sheets.push(await reducedMotion(browser, url, findings));
} finally {
  await browser.close();
  for (const s of servers) s.close();
}

const rel = (f) => (f.startsWith(process.cwd() + path.sep) ? path.relative(process.cwd(), f) : f);
const lines = [
  '# Site check', '',
  `Opened \`${target}\` in ${chromium.name()} at 1440×900 and 390×844, scrolled in ${steps} steps.`, '',
  findings.length ? `## Problems found (${findings.length})` : '## No automatic problems found', '',
  ...findings.map((f) => `- ${f}`), '',
  '## Look at these (required)', '',
  ...sheets.map((f) => `- \`${rel(f)}\``), '',
  'Automatic checks cannot see whether an effect looks right. Open each sheet and compare',
  'every section against the approved design (and the reference column, when present):',
  'parallax depth, pinned sections, sideways galleries fully visible, text reveals finishing,',
  'nothing cut off at the edges, phone layout readable.',
];
fs.writeFileSync(path.join(out, 'report.md'), lines.join('\n') + '\n');
fs.writeFileSync(path.join(out, 'report.json'), JSON.stringify({ target, findings, sheets: sheets.map(rel) }, null, 2));
console.log(lines.join('\n'));
process.exit(findings.length ? 1 : 0);

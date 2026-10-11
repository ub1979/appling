#!/usr/bin/env node
// Appling deck check: open a reveal.js deck in a real browser, show every
// slide with all of its build-up steps, and save what an audience would see.
//
//   node deck-check.mjs [deck-folder|index.html|http://url] [--pdf deck.pdf]
//                       [--out .lyra/qa/deck-check] [--min-font 16] [--max-words 45]
//
// It reports console/page errors, failed requests, content that spills off
// the slide, text smaller than --min-font (slide pixels, before scaling) and
// slides with more than --max-words words on screen (speaker notes excluded).
// It writes one screenshot per slide plus `sheet.png`, and with --pdf it
// exports the deck through reveal.js's print mode (one page per slide).
//
// Exit codes: 0 = no problems found, 1 = problems found, 3 = BLOCKED (no browser
// or no reveal.js deck). The browser is the installed Google Chrome (or Edge, or
// Playwright's Chromium); `playwright-core` is fetched once into a shared cache.

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
const out = path.resolve(opt('--out', fs.existsSync('.lyra') ? '.lyra/qa/deck-check' : 'deck-check-report'));
const pdf = opt('--pdf', null);
// 16 slide-pixels (about 2.2% of a 720 px slide) is the floor for labels and
// sources to stay legible on a projector; body text should be 24 or more.
const minFont = Number(opt('--min-font', 16)) || 16;
// ~45 words is where a slide stops being glanceable and becomes a document.
const maxWords = Number(opt('--max-words', 45)) || 45;
const target = args[0] || (fs.existsSync('dist/index.html') ? 'dist' : 'index.html');

function blocked(msg) {
  console.log(`BLOCKED: ${msg}`);
  fs.mkdirSync(out, { recursive: true });
  fs.writeFileSync(path.join(out, 'report.md'), `# Deck check\n\n**BLOCKED** — ${msg}\n`);
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
  '.woff': 'font/woff', '.ttf': 'font/ttf', '.mp4': 'video/mp4', '.webm': 'video/webm', '.ico': 'image/x-icon' };

function serve(dir) {
  return new Promise((resolve) => {
    const server = createServer((req, res) => {
      const rel = decodeURIComponent(new URL(req.url, 'http://x').pathname);
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
  if (!fs.existsSync(abs)) blocked(`nothing to open at ${spec}.`);
  const dir = fs.statSync(abs).isDirectory() ? abs : path.dirname(abs);
  const page = fs.statSync(abs).isDirectory() ? '' : path.basename(abs);
  const server = await serve(dir);
  servers.push(server);
  return `http://127.0.0.1:${server.address().port}/${page}`;
}

async function waitForReveal(page) {
  const ok = await page.waitForFunction(() => window.Reveal && window.Reveal.isReady && window.Reveal.isReady(),
    null, { timeout: 15000 }).then(() => true, () => false);
  if (!ok) blocked('the page did not start a reveal.js deck (window.Reveal never became ready).');
}

// In-page probes: show slide (h, v) with every fragment visible; once it has
// settled, measure it.
function showSlide({ h, v }) {
  window.Reveal.slide(h, v);
  window.Reveal.getCurrentSlide().querySelectorAll('.fragment').forEach((f) => f.classList.add('visible'));
}

function probeSlide({ minFont }) {
  const R = window.Reveal;
  const slide = R.getCurrentSlide();
  const box = document.querySelector('.reveal .slides').getBoundingClientRect();
  const scale = R.getScale ? R.getScale() : 1;
  const label = (el) => `${el.tagName.toLowerCase()}${el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : ''}`;
  const spill = [];
  const small = [];
  const shown = (el) => {
    for (let p = el; p && p !== slide.parentElement; p = p.parentElement) {
      const s = getComputedStyle(p);
      if (s.display === 'none' || s.visibility === 'hidden' || Number(s.opacity) === 0) return false;
    }
    return true;
  };
  for (const el of slide.querySelectorAll('*')) {
    if (el.closest('aside.notes') || el.closest('[aria-hidden="true"]') || !shown(el)) continue;
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) continue;
    const own = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim().length > 2);
    // Only content counts: text, tables and pictures. Decorative shapes and
    // full-bleed backgrounds may run past the edge on purpose.
    const media = el.matches('img, video, canvas, table') && r.width < box.width * 0.95 && r.height < box.height * 0.95;
    if ((own || media) && (r.left < box.left - 2 || r.right > box.right + 2 || r.top < box.top - 2 || r.bottom > box.bottom + 2)) {
      if (spill.length < 4) spill.push(`${label(el)}${own ? ` "${el.textContent.trim().slice(0, 30)}"` : ''}`);
    }
    if (own) {
      const px = parseFloat(getComputedStyle(el).fontSize);
      if (px < minFont && small.length < 4) small.push(`${label(el)} ${Math.round(px)}px "${el.textContent.trim().slice(0, 30)}"`);
    }
  }
  const clone = slide.cloneNode(true);
  clone.querySelectorAll('aside.notes, script, style').forEach((n) => n.remove());
  const words = (clone.textContent || '').trim().split(/\s+/).filter((w) => /\w/.test(w)).length;
  const title = (slide.querySelector('h1, h2, h3')?.textContent || '').trim().slice(0, 50);
  return { spill, small, words, title, scale };
}

async function contactSheet(browser, shots, width, height) {
  const w = 400;
  const h = Math.round((w * height) / width);
  const cells = shots.map((s) => `<figure><img src="data:image/png;base64,${fs.readFileSync(s.file).toString('base64')}"><figcaption>${s.n}. ${s.title.replace(/</g, '&lt;')}</figcaption></figure>`).join('');
  const html = `<style>body{margin:0;padding:12px;background:#111;color:#ddd;font:12px system-ui}
    main{display:grid;grid-template-columns:repeat(4,${w}px);gap:10px}figure{margin:0}
    img{width:${w}px;height:${h}px;object-fit:contain;display:block;border:1px solid #333;background:#000}
    figcaption{padding:3px 0}</style><main>${cells}</main>`;
  const page = await browser.newPage({ viewport: { width: 4 * (w + 10) + 24, height: 600 } });
  await page.setContent(html);
  const file = path.join(out, 'sheet.png');
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
let sheet = null;
let pdfFile = null;
let count = 0;
try {
  const url = await urlFor(target, servers);
  // Read the deck's own size first so the window matches it (scale ≈ 1).
  const probe = await browser.newPage();
  await probe.goto(url, { waitUntil: 'load', timeout: 30000 });
  await waitForReveal(probe);
  const cfg = await probe.evaluate(() => ({ width: Number(Reveal.getConfig().width) || 960, height: Number(Reveal.getConfig().height) || 700 }));
  await probe.close();

  const ctx = await browser.newContext({ viewport: cfg, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  const errors = [];
  const failed = [];
  page.on('console', (m) => { if (m.type() === 'error' && !/status of 404/.test(m.text())) errors.push(m.text().slice(0, 200)); });
  page.on('pageerror', (e) => errors.push(String(e.message || e).slice(0, 200)));
  page.on('requestfailed', (r) => /favicon\.ico$/.test(r.url()) || failed.push(`${r.url().slice(0, 120)} (${r.failure()?.errorText || 'failed'})`));
  page.on('response', (r) => { if (r.status() >= 400 && !/favicon\.ico$/.test(r.url())) failed.push(`${r.url().slice(0, 120)} (HTTP ${r.status()})`); });
  await page.goto(url, { waitUntil: 'load', timeout: 30000 });
  await waitForReveal(page);
  await page.waitForLoadState('networkidle', { timeout: 8000 }).catch(() => {});
  // Transitions off so each screenshot shows the finished slide.
  await page.evaluate(() => Reveal.configure({ transition: 'none', backgroundTransition: 'none' }));
  const slides = await page.evaluate(() => Reveal.getSlides().map((s) => {
    const i = Reveal.getIndices(s);
    return { h: i.h, v: i.v || 0 };
  }));
  const shots = [];
  for (const [i, s] of slides.entries()) {
    await page.evaluate(showSlide, s);
    await page.waitForTimeout(700); // let fragment and auto-animate styles settle
    const r = await page.evaluate(probeSlide, { minFont });
    const n = i + 1;
    const file = path.join(out, `slide-${String(n).padStart(2, '0')}.png`);
    await page.screenshot({ path: file });
    shots.push({ file, n, title: r.title });
    const tag = `[slide ${n}${r.title ? ` "${r.title}"` : ''}]`;
    if (r.spill.length) findings.push(`${tag} Content runs off the slide: ${r.spill.join('; ')}`);
    if (r.small.length) findings.push(`${tag} Text smaller than ${minFont}px: ${r.small.join('; ')}`);
    if (r.words > maxWords) findings.push(`${tag} ${r.words} words on screen (over ${maxWords}); move detail to speaker notes`);
  }
  count = slides.length;
  for (const e of [...new Set(errors)]) findings.push(`Console/page error: ${e}`);
  for (const f of [...new Set(failed)]) findings.push(`Failed request: ${f}`);
  await ctx.close();
  sheet = await contactSheet(browser, shots, cfg.width, cfg.height);

  if (pdf) {
    const printCtx = await browser.newContext({ viewport: cfg });
    const pp = await printCtx.newPage();
    // One page per slide with every build-up step shown, whatever the deck's
    // own pdfSeparateFragments setting is.
    await pp.addInitScript(() => {
      let deck;
      Object.defineProperty(window, 'Reveal', { configurable: true, get: () => deck, set: (value) => {
        deck = value;
        const init = value && value.initialize;
        if (typeof init === 'function') value.initialize = (o = {}) => init.call(value, { ...o, pdfSeparateFragments: false });
      } });
    });
    const sep = url.includes('?') ? '&' : '?';
    await pp.goto(url.replace(/(#.*)?$/, `${sep}print-pdf`), { waitUntil: 'load', timeout: 30000 });
    await waitForReveal(pp);
    await pp.waitForLoadState('networkidle', { timeout: 8000 }).catch(() => {});
    await pp.waitForTimeout(800);
    pdfFile = path.resolve(pdf);
    await pp.pdf({ path: pdfFile, printBackground: true, preferCSSPageSize: true,
      width: `${cfg.width}px`, height: `${cfg.height}px` });
    await printCtx.close();
  }
} finally {
  await browser.close();
  for (const s of servers) s.close();
}

const rel = (f) => (f.startsWith(process.cwd() + path.sep) ? path.relative(process.cwd(), f) : f);
const lines = [
  '# Deck check', '',
  `Opened \`${target}\` in ${chromium.name()}: ${count} slides, every build-up step shown.`, '',
  findings.length ? `## Problems found (${findings.length})` : '## No automatic problems found', '',
  ...findings.map((f) => `- ${f}`), '',
  '## Look at these (required)', '',
  `- \`${rel(sheet)}\` (one screenshot per slide is next to it)`,
  ...(pdfFile ? [`- \`${rel(pdfFile)}\` (PDF export)`] : []), '',
  'Automatic checks cannot judge the story or the design. Open the sheet and check each',
  'slide: one idea, a headline that states the point, nothing cramped, consistent layout.',
];
fs.writeFileSync(path.join(out, 'report.md'), lines.join('\n') + '\n');
fs.writeFileSync(path.join(out, 'report.json'), JSON.stringify({ target, slides: count, findings, sheet: rel(sheet), pdf: pdfFile && rel(pdfFile) }, null, 2));
console.log(lines.join('\n'));
process.exit(findings.length ? 1 : 0);

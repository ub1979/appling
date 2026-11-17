/** Run explicit browser journeys and save machine-readable evidence.
 * node browser-check.mjs --url http://127.0.0.1:5173 --spec checks.json --out .sdlc/evidence/browser
 * Spec: { journeys: [{name, steps: [{action:'click', role:'button', name:'Add'},
 *   {action:'expectText', selector:'#count', text:'1'}]}] }
 */
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { chromium } from 'playwright';

const arg = (name) => process.argv[process.argv.indexOf(name) + 1];
if (!process.argv.includes('--url') || !process.argv.includes('--spec') || !process.argv.includes('--out')) {
  throw new Error('Required: --url URL --spec FILE --out DIRECTORY');
}
const url = arg('--url');
const spec = JSON.parse(await readFile(arg('--spec'), 'utf8'));
const output = path.resolve(arg('--out'));
if (!Array.isArray(spec.journeys) || spec.journeys.length === 0) throw new Error('At least one explicit journey is required.');
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true });
const report = { url, started: new Date().toISOString(), browser: 'chromium', journeys: [], consoleErrors: [], failedRequests: [] };
let failed = false;
try {
  for (const [index, journey] of spec.journeys.entries()) {
    const context = await browser.newContext({ viewport: journey.viewport ?? { width: 1280, height: 800 } });
    const page = await context.newPage();
    page.on('pageerror', (error) => report.consoleErrors.push(String(error)));
    page.on('requestfailed', (request) => report.failedRequests.push({ url: request.url(), error: request.failure()?.errorText }));
    const result = { name: journey.name, steps: [], passed: false };
    try {
      await page.goto(new URL(journey.path ?? '/', url).href, { waitUntil: 'networkidle', timeout: 30000 });
      if (!journey.steps?.length) throw new Error('A journey needs at least one action/assertion.');
      for (const step of journey.steps) {
        const locator = step.role ? page.getByRole(step.role, { name: step.name, exact: true }) : step.label ? page.getByLabel(step.label, { exact: true }) : page.locator(step.selector ?? 'body');
        switch (step.action) {
          case 'click': await locator.click(); break;
          case 'fill': await locator.fill(step.value); break;
          case 'press': await locator.press(step.key); break;
          case 'reload': await page.reload({ waitUntil: 'networkidle' }); break;
          case 'expectText': await locator.filter({ hasText: step.text }).first().waitFor({ state: 'visible' }); break;
          case 'expectVisible': await locator.waitFor({ state: 'visible' }); break;
          case 'expectHidden': await locator.waitFor({ state: 'hidden' }); break;
          case 'expectValue': {
            const actual = await locator.inputValue();
            if (actual !== step.value) throw new Error(`Expected value ${step.value}, received ${actual}`);
            break;
          }
          default: throw new Error(`Unsupported browser action: ${step.action}`);
        }
        result.steps.push({ ...step, passed: true });
      }
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1);
      if (overflow) throw new Error('Page has horizontal overflow at the tested viewport.');
      result.passed = true;
    } catch (error) {
      result.error = String(error); failed = true;
    } finally {
      result.screenshot = `journey-${index + 1}.png`;
      await page.screenshot({ path: path.join(output, result.screenshot), fullPage: true }).catch(() => {});
      report.journeys.push(result); await context.close();
    }
  }
} finally {
  await browser.close();
  report.passed = !failed && report.consoleErrors.length === 0 && report.failedRequests.length === 0;
  await writeFile(path.join(output, 'browser-report.json'), JSON.stringify(report, null, 2) + '\n');
}
console.log(JSON.stringify(report));
process.exitCode = report.passed ? 0 : 1;

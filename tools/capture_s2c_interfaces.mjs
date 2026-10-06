import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const runtime = process.env.CODEX_NODE_PACKAGES;
assert.ok(runtime, 'CODEX_NODE_PACKAGES is required');
const {chromium} = createRequire(path.join(runtime, 'package.json'))('playwright');
const work = path.join(root, 'output/s2c-authoring');
const folder = path.join(root, 'docs/submission/figures/s2c-ui');
const base = 'http://127.0.0.1:8875';
const cookie = JSON.parse(await fs.readFile(path.join(work, 'capture-session.json'), 'utf8'));
const files = ['index.html', 'app.js', 'styles.css', 'prism-v2.css', 'research-workbench.css', 'research-tools.js'];
const staticHashes = {};
for (const filename of files) {
  const local = await fs.readFile(path.join(root, 'app/api/static', filename));
  const url = filename === 'index.html' ? base + '/' : base + '/static/' + filename;
  const response = await fetch(url, {headers: {Cookie: `${cookie.name}=${cookie.value}`}});
  assert.equal(response.status, 200);
  const served = Buffer.from(await response.arrayBuffer());
  assert.deepEqual(served, local, 'Current service file differs: ' + filename);
  staticHashes[filename] = createHash('sha256').update(local).digest('hex');
}
await fs.mkdir(folder, {recursive: true});
const browser = await chromium.launch({channel: 'msedge', headless: true});
const errors = [];
const apiStatuses = new Map();
const screenshots = [];
try {
  const context = await browser.newContext({viewport: {width: 1440, height: 960}, deviceScaleFactor: 2});
  await context.addCookies([cookie]);
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  page.on('response', response => {
    const url = new URL(response.url());
    if (url.origin === base && url.pathname.startsWith('/api/')) apiStatuses.set(url.pathname, response.status());
  });
  await page.goto(base + '/#copilot', {waitUntil: 'networkidle', timeout: 60000});
  await page.waitForFunction(() => !document.body.classList.contains('questionnaire-pending'));
  assert.equal(await page.evaluate(() => Boolean(window.PRISM_PAGES_SNAPSHOT)), false);
  for (const [name, route, selector] of [
    ['copilot', 'copilot', '#copilot'],
    ['portfolio', 'overview', '#overview'],
    ['profile', 'profile', '#profile'],
    ['market', 'market', '#market'],
    ['research-workbench', 'research-workbench', '#research-workbench'],
    ['skill-store', 'skill-store', '#skill-store'],
  ]) {
    await page.evaluate(route => {location.hash = route;}, route);
    await page.locator(selector).waitFor({state: 'visible'});
    await page.waitForLoadState('networkidle');
    await page.evaluate(async () => {
      window.scrollTo(0, 0);
      await document.fonts.ready;
      await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    });
    const status = await page.evaluate(selector => ({
      route: location.hash, text: document.querySelector(selector).innerText,
      width: document.documentElement.clientWidth, scrollWidth: document.documentElement.scrollWidth,
      snapshot: Boolean(window.PRISM_PAGES_SNAPSHOT),
      openDialogs: [...document.querySelectorAll('dialog[open]')].map(item => item.id),
    }), selector);
    assert.ok(status.text.length > 30);
    assert.ok(status.scrollWidth <= status.width);
    assert.deepEqual(status.openDialogs, []);
    assert.equal(status.snapshot, false);
    const filename = name + '-20261005.png';
    await page.screenshot({path: path.join(folder, filename)});
    screenshots.push({filename, route, viewport: {width: 1440, height: 960}, deviceScaleFactor: 2,
      sha256: createHash('sha256').update(await fs.readFile(path.join(folder, filename))).digest('hex'),
      visible_text: status.text});
    console.log(JSON.stringify({name, route, textLength: status.text.length}));
  }
  assert.deepEqual(errors, []);
  for (const url of ['/api/v1/auth/context', '/api/v1/advisor/portfolio/current', '/api/v1/advisor/profile/summary']) {
    assert.equal(apiStatuses.get(url), 200, 'Required current-data API: ' + url);
  }
  const health = await (await context.request.get(base + '/api/health')).json();
  assert.equal(health.status, 'ok');
  assert.equal(health.data_mode, 'LIVE');
  const report = {captured_at: new Date().toISOString(), source: 'current-local-service',
    service: base, database: 'SQLite backup of existing confirmed local data', snapshot_adapter: false,
    browser_errors: errors, api_statuses: Object.fromEntries(apiStatuses), static_sha256: staticHashes,
    screenshots};
  await fs.writeFile(path.join(work, 'interface-capture.json'), JSON.stringify(report, null, 2));
  const provenance = {...report, screenshots: screenshots.map(({visible_text, ...item}) => item)};
  await fs.writeFile(path.join(folder, 'capture-manifest.json'), JSON.stringify(provenance, null, 2) + '\n');
} finally {
  await browser.close();
}

import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const runtime = process.env.CODEX_NODE_PACKAGES;
assert.ok(runtime);
const {chromium} = createRequire(path.join(runtime, 'package.json'))('playwright');
const filename = path.join(root, 'docs/submission/figures/s2c-shared/system-architecture.svg');
const browser = await chromium.launch({channel: 'msedge', headless: true});
try {
  const page = await browser.newPage({viewport: {width: 2700, height: 1600}, deviceScaleFactor: 2});
  await page.setContent('<html><body style="margin:0;background:white"></body></html>');
  await page.evaluate(async source => {
    const parsed = new DOMParser().parseFromString(source, 'image/svg+xml');
    if (parsed.querySelector('parsererror')) throw Error('Invalid SVG');
    document.body.appendChild(document.importNode(parsed.documentElement, true));
    await document.fonts.ready;
  }, await fs.readFile(filename, 'utf8'));
  await page.locator('svg').screenshot({path: filename.replace(/\.svg$/, '.png')});
} finally {
  await browser.close();
}

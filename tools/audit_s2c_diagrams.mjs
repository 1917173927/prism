import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {inspectDiagramGeometry} from './s2c_diagram_geometry.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const runtime = process.env.CODEX_NODE_PACKAGES;
assert.ok(runtime);
const {chromium} = createRequire(path.join(runtime, 'package.json'))('playwright');
const work = path.join(root, 'output/s2c-authoring');
const build = JSON.parse(await fs.readFile(path.join(work, 'build-report.json'), 'utf8'));
const browser = await chromium.launch({channel: 'msedge', headless: true});
const figures = [];
try {
  const page = await browser.newPage({viewport: {width: 3000, height: 3200}});
  for (const figure of build.figures) {
    if (path.basename(path.dirname(figure.source)) === 's2c-ui') continue;
    const filename = figure.source.replace(/\.png$/, '.svg');
    const source = await fs.readFile(filename, 'utf8');
    await page.setContent('<html><body style="margin:0"></body></html>');
    await page.evaluate(async source => {
      const parsed = new DOMParser().parseFromString(source, 'image/svg+xml');
      if (parsed.querySelector('parsererror')) throw Error('Invalid SVG');
      document.body.appendChild(document.importNode(parsed.documentElement, true));
      await document.fonts.ready;
    }, source);
    const result = await page.evaluate(inspectDiagramGeometry);
    figures.push({source: path.relative(root, filename),
      svg_sha256: createHash('sha256').update(source).digest('hex'),
      png_sha256: createHash('sha256').update(await fs.readFile(figure.source)).digest('hex'), ...result});
    console.log(JSON.stringify({name: path.basename(filename), texts: result.text_count, lines: result.line_count,
      collisions: result.collisions}));
  }
} finally {
  await browser.close();
}
const status = figures.every(figure => figure.collisions.length === 0) ? 'PASS' : 'FAILED';
await fs.writeFile(path.join(work, 'diagram-overlap-audit.json'), JSON.stringify({status, figures}, null, 2));
if (process.argv.includes('--check')) assert.ok(figures.every(figure => figure.collisions.length === 0), 'Diagram text overlaps visible connectors');

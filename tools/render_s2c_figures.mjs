import fs from 'node:fs/promises';
import path from 'node:path';
import http from 'node:http';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const runtime = process.env.CODEX_NODE_PACKAGES;
assert.ok(runtime, 'CODEX_NODE_PACKAGES is required');
const {chromium} = createRequire(path.join(runtime, 'package.json'))('playwright');
const modules = path.join(root, 'output/report-review/node_modules');
const folder = path.join(root, 'docs/submission/figures/s2c');
const server = http.createServer(async (request, response) => {
  if (request.url === '/') {
    response.setHeader('Content-Type', 'text/html; charset=utf-8');
    response.end('<html><body style="margin:0;background:white"></body></html>');
    return;
  }
  if (request.url === '/favicon.ico') { response.writeHead(204).end(); return; }
  const filename = path.resolve(modules, '.' + decodeURIComponent(request.url));
  assert.ok(filename.startsWith(modules + path.sep));
  response.setHeader('Content-Type', 'text/javascript');
  response.end(await fs.readFile(filename));
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const browser = await chromium.launch({channel: 'msedge', headless: true});
try {
  const page = await browser.newPage({viewport: {width: 2000, height: 2400}, deviceScaleFactor: 2});
  await page.goto(`http://127.0.0.1:${server.address().port}`);
  await page.evaluate(async () => {
    const {default: mermaid} = await import('/mermaid/dist/mermaid.esm.min.mjs');
    mermaid.initialize({startOnLoad: false, theme: 'base', securityLevel: 'strict',
      themeVariables: {fontFamily: 'Microsoft YaHei', fontSize: '20px', primaryColor: '#fff7ed',
        primaryTextColor: '#202b3c', primaryBorderColor: '#d38a46', lineColor: '#62748c',
        clusterBkg: '#f1f5f9', clusterBorder: '#b8c6d7', edgeLabelBackground: '#ffffff'},
      flowchart: {htmlLabels: false, curve: 'linear', nodeSpacing: 24, rankSpacing: 38, padding: 16}});
    window.renderer = mermaid;
  });
  const names = (await fs.readdir(folder)).filter(name => name.endsWith('.mmd')).sort();
  for (const filename of names) {
    const source = await fs.readFile(path.join(folder, filename), 'utf8');
    const result = await page.evaluate(async source => {
      const {svg} = await window.renderer.render('s2cFigure', source);
      document.body.innerHTML = '<div id="figure" style="display:inline-block;padding:16px;background:white">' + svg + '</div>';
      const element = document.querySelector('svg');
      element.style.maxWidth = 'none';
      element.setAttribute('width', element.viewBox.baseVal.width);
      element.setAttribute('height', element.viewBox.baseVal.height);
      await document.fonts.ready;
      const missingLabels = [...element.querySelectorAll('.node')].filter(node => !node.textContent.trim()).length;
      return {svg: new XMLSerializer().serializeToString(element), missingLabels,
        width: element.viewBox.baseVal.width, height: element.viewBox.baseVal.height};
    }, source);
    assert.equal(result.missingLabels, 0);
    const name = path.basename(filename, '.mmd');
    await fs.writeFile(path.join(folder, name + '.svg'), result.svg);
    await page.locator('#figure').screenshot({path: path.join(folder, name + '.png')});
    console.log(JSON.stringify({name, width: result.width, height: result.height}));
  }
} finally {
  await browser.close();
  await new Promise(resolve => server.close(resolve));
}

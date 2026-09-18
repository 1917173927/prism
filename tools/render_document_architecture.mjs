import fs from 'node:fs/promises';
import path from 'node:path';
import http from 'node:http';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
import puppeteer from 'puppeteer-core';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const modules = path.join(root, 'output/report-review/node_modules');
const server = http.createServer(async (request,response) => {
  if(request.url === '/') {
    response.setHeader('Content-Type','text/html; charset=utf-8');
    response.end('<html><body></body></html>');
    return;
  }
  if(request.url === '/favicon.ico') { response.writeHead(204).end(); return; }
  const file = path.resolve(modules, '.'+decodeURIComponent(request.url));
  assert.ok(file.startsWith(modules+path.sep));
  response.setHeader('Content-Type','text/javascript');
  response.end(await fs.readFile(file));
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const browser=await puppeteer.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
try {
  const page=await browser.newPage();
  await page.setViewport({width:1800,height:2200,deviceScaleFactor:2});
  await page.goto(`http://127.0.0.1:${server.address().port}`);
  await page.evaluate(async()=>{
    const {default:mermaid}=await import('/mermaid/dist/mermaid.esm.min.mjs');
    mermaid.initialize({startOnLoad:false,theme:'base',securityLevel:'strict',
      themeVariables:{fontFamily:'Microsoft YaHei',fontSize:'17px',primaryColor:'#ffffff',primaryTextColor:'#202124',lineColor:'#717780',clusterBkg:'#f6f7f9',clusterBorder:'#d5d9df'},
      flowchart:{htmlLabels:false,curve:'linear',nodeSpacing:35,rankSpacing:48,padding:18}});
    window.renderer=mermaid;
  });
  for(const name of ['frontend-framework','backend-framework','context-dataflow']) {
    const folder=path.join(root,'docs/submission/figures');
    const source=await fs.readFile(path.join(folder,name+'.mmd'),'utf8');
    const svg=await page.evaluate(async(source)=>{
      const {svg}=await window.renderer.render('architecture',source);
      document.body.style.cssText='margin:0;padding:24px;background:white';
      document.body.innerHTML='<div id="figure" style="display:inline-block">'+svg+'</div>';
      const element=document.querySelector('svg');
      element.style.maxWidth='none';
      element.style.width=element.viewBox.baseVal.width+'px';
      await document.fonts.ready;
      return element.outerHTML;
    },source);
    await fs.writeFile(path.join(folder,name+'.svg'),svg);
    await (await page.$('#figure')).screenshot({path:path.join(folder,name+'.png')});
    console.log(name);
  }
} finally {
  await browser.close();
  server.close();
}

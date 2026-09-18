import fs from 'node:fs/promises';
import path from 'node:path';
import http from 'node:http';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
import puppeteer from 'puppeteer-core';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const figures = [
  {name:'frontend-framework', title:'前端交互与状态流转', subtitle:'页面入口 → 状态协调 → 服务通信 → 结果呈现', tag:'图 5-2 · 前端框架'},
  {name:'backend-framework', title:'后端分层服务框架', subtitle:'应用服务组织任务，领域模块执行计算与审查', tag:'图 5-3 · 后端框架'},
  {name:'context-dataflow', title:'从用户追问到工具处理', subtitle:'请求入口核验前提，按问题类型选择处理路径', tag:'图 5-8 · 对话流程'},
];
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
      themeVariables:{fontFamily:'Microsoft YaHei',fontSize:'17px',primaryColor:'#ffffff',primaryTextColor:'#202124',lineColor:'#858b94',clusterBkg:'#f5f6f8',clusterBorder:'#e3e6eb',edgeLabelBackground:'#ffffff'},
      themeCSS:'.cluster-label text{font-weight:700;fill:#626975!important}.cluster rect{rx:12;ry:12}.node rect{rx:8;ry:8}.edgeLabel{font-size:14px}.flowchart-link{stroke-width:1.5px}',
      flowchart:{htmlLabels:false,curve:'stepBefore',nodeSpacing:30,rankSpacing:44,padding:20}});
    window.renderer=mermaid;
  });
  for(const figure of figures) {
    const {name}=figure;
    const folder=path.join(root,'docs/submission/figures');
    const source=await fs.readFile(path.join(folder,name+'.mmd'),'utf8');
    const svg=await page.evaluate(async({source,figure})=>{
      const {svg}=await window.renderer.render('architecture',source);
      document.body.style.cssText='margin:0;padding:24px;background:white';
      document.body.innerHTML='<div id="figure" style="display:inline-block">'+svg+'</div>';
      const element=document.querySelector('svg');
      element.style.maxWidth='none';
      element.style.width=element.viewBox.baseVal.width+'px';
      await document.fonts.ready;
      const namespace='http://www.w3.org/2000/svg';
      const bounds=element.viewBox.baseVal;
      const drawingWidth=bounds.width;
      const drawingHeight=bounds.height;
      const margin=32;
      const header=132;
      const footer=66;
      const width=Math.max(820,drawingWidth+margin*2);
      const height=drawingHeight+header+footer;
      const canvas=document.createElementNS(namespace,'svg');
      canvas.setAttribute('xmlns',namespace);
      canvas.setAttribute('viewBox',`0 0 ${width} ${height}`);
      canvas.setAttribute('width',String(width));
      canvas.setAttribute('height',String(height));
      const add=(tag,attributes,text)=>{
        const item=document.createElementNS(namespace,tag);
        for(const [key,value] of Object.entries(attributes))item.setAttribute(key,String(value));
        if(text)item.textContent=text;
        canvas.appendChild(item);
        return item;
      };
      add('rect',{width,height,fill:'#ffffff'});
      const label=(x,y,size,fill,weight,text)=>add('text',{x,y,'font-size':size,fill,'font-weight':weight,'font-family':'Microsoft YaHei'},text);
      label(margin,26,12,'#c86200',700,'PRISM  /  技术文档');
      const tag=label(width-margin,26,12,'#757b85',400,figure.tag);
      tag.setAttribute('text-anchor','end');
      label(margin,63,27,'#252931',700,figure.title);
      label(margin,92,14,'#69717d',400,figure.subtitle);
      add('line',{x1:margin,y1:112,x2:width-margin,y2:112,stroke:'#e4e7eb'});
      add('line',{x1:margin,y1:112,x2:margin+48,y2:112,stroke:'#e86f00','stroke-width':3});
      element.setAttribute('x',String((width-drawingWidth)/2));
      element.setAttribute('y',String(header));
      element.setAttribute('width',String(drawingWidth));
      element.setAttribute('height',String(drawingHeight));
      canvas.appendChild(element);
      const legendY=height-23;
      add('line',{x1:margin,y1:height-48,x2:width-margin,y2:height-48,stroke:'#e4e7eb'});
      for(const [x,fill,stroke,text] of [[margin,'#292d34','#292d34','入口'],[margin+120,'#fff1e3','#e86f00','关键处理'],[margin+275,'#ffffff','#cbd0d6','支撑模块']]){
        add('rect',{x,y:legendY-10,width:13,height:13,rx:3,fill,stroke});
        label(x+22,legendY+1,12,'#69717d',400,text);
      }
      document.querySelector('#figure').replaceChildren(canvas);
      return new XMLSerializer().serializeToString(canvas);
    },{source,figure});
    await fs.writeFile(path.join(folder,name+'.svg'),svg);
    await (await page.$('#figure')).screenshot({path:path.join(folder,name+'.png')});
    console.log(name);
  }
} finally {
  await browser.close();
  server.close();
}

import fs from 'node:fs/promises';
import path from 'node:path';
import http from 'node:http';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {fileURLToPath} from 'node:url';
import {randomUUID} from 'node:crypto';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const runtime = process.env.CODEX_NODE_PACKAGES;
assert.ok(runtime, 'CODEX_NODE_PACKAGES is required');
const {chromium} = createRequire(path.join(runtime, 'package.json'))('playwright');
const modules = path.join(root, 'output/report-review/node_modules');
const folder = path.join(root, 'docs/submission/figures/s2c');
const work = path.join(root, 'output/s2c-authoring');
const descriptions = {
  'business-dataflow': ['业务资料与分析处理', '输入条件、处理模块与保存对象按业务职责组织'],
  'model-responsibilities': ['模型与确定性计算职责', '模型理解问题，工具执行查询与计算，结果接受条件检查'],
  'interface-task-cycle': ['界面任务与操作反馈', '用户准备输入、提交任务并根据结果状态继续操作'],
  'data-lifecycle': ['资料生命周期与版本检查', '资料确认、当前版本使用与历史查询保留各自条件'],
  'provider-provenance': ['金融记录与来源信息', '主体、单位、时间和来源随查询结果继续传递'],
  'optimization-run': ['组合优化与目标配置', '当前组合按已确认画像预算生成确定性目标结构'],
  'research-fact-trace': ['研究节点事实追溯', '请求、响应与输入版本共同说明一次观测的来源'],
  'workflow-user-journey': ['个人分析与研究操作', '业务路径按资料条件执行，结果保留来源与处理状态'],
  'prompt-composition': ['提示词组织与工具处理', '当前问题、已确认资料与工具结果共同参与对话'],
  'frontend-framework': ['前端交互与状态框架', '页面输入、状态协调与结果呈现分别组织'],
  'backend-framework': ['后端分层服务框架', '应用服务、领域处理及外部资源具有明确职责'],
  'workspace-navigation': ['工作台页面入口与反馈', '六个页面按任务组织，状态和资料条件独立展示'],
  'database-relations': ['数据库外键与记录归属', '每一行说明一组数据库关联及其校验条件'],
  'database-version-relations': ['资料版本与应用层关联', '资料版本、个人前提和决策引用分别核验'],
  'provider-states': ['金融数据状态管理', '请求结果保留来源、资料范围与处理状态'],
  'profile-rules': ['画像与预算参与组合计算', '正式评分与用户确认形成风险计算条件'],
  'exposure-calculation': ['持仓穿透与集中度计算', '金额、披露贡献与画像预算使用明确口径'],
  'research-runtime': ['研究依赖执行与时间预算', '数值为单进程默认限制，外部额度分别核查'],
  'knowledge-retrieval': ['研究资料提取与检索', '混合检索默认关闭，金融声明继续接受来源验证'],
  'context-dataflow': ['会话上下文与工具处理', '当前前提决定个人组合问题的处理条件'],
  'session-premises': ['会话前提确认与变化检查', '用户确认、持续核对和重新确认保留各自状态'],
  'research-algorithms': ['确定性研究算法', '真实输入与计算条件由 Pydantic 校验'],
};
const blockStyles = `
classDef section fill:#ffffff,stroke:none,color:#202124,font-weight:bold;
classDef container fill:#ffffff,stroke:none;
classDef neutral fill:#fafafa,stroke:#dedfe2,color:#202124;
classDef accent fill:#fff4e8,stroke:#f1c89e,color:#202124;
classDef success fill:#eef7f1,stroke:#a8c8b4,color:#202124;
classDef failure fill:#fbefef,stroke:#d9b1b1,color:#202124;
`;
async function saveArtifact(filename, content) {
  const temporary = path.join(work, randomUUID() + path.extname(filename));
  await fs.writeFile(temporary, content);
  await fs.rename(temporary, filename);
}
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
    mermaid.initialize({startOnLoad: false, theme: 'base', securityLevel: 'strict', htmlLabels: false,
      themeVariables: {fontFamily: 'Microsoft YaHei', fontSize: '20px', primaryColor: '#fafafa',
        primaryTextColor: '#202b3c', primaryBorderColor: '#d38a46', lineColor: '#62748c',
        clusterBkg: '#f1f5f9', clusterBorder: '#b8c6d7', edgeLabelBackground: '#ffffff'},
      flowchart: {curve: 'linear', nodeSpacing: 32, rankSpacing: 38, padding: 20,
        subGraphTitleMargin: {top: 12, bottom: 12}}});
    window.renderer = mermaid;
  });
  const selected = process.argv.slice(2);
  const names = (await fs.readdir(folder)).filter(name => name.endsWith('.mmd') && (!selected.length || selected.includes(path.basename(name, '.mmd')))).sort();
  for (const filename of names) {
    const source = await fs.readFile(path.join(folder, filename), 'utf8');
    const name = path.basename(filename, '.mmd');
    const result = await page.evaluate(async ({source, description}) => {
      const {svg} = await window.renderer.render('s2cFigure', source);
      document.body.innerHTML = '<div id="figure" style="display:inline-block;padding:16px;background:white">' + svg + '</div>';
      const element = document.querySelector('svg');
      element.style.maxWidth = 'none';
      element.setAttribute('width', element.viewBox.baseVal.width);
      element.setAttribute('height', element.viewBox.baseVal.height);
      await document.fonts.ready;
      if (source.startsWith('block')) {
        const stages = ['input', 'process', 'output'].map(id => {
          const node = element.querySelector(`#s2cFigure-${id}`);
          const matrix = node.transform.baseVal.consolidate().matrix;
          const box = node.querySelector('rect').getBBox();
          return {center: matrix.f, top: matrix.f + box.y, bottom: matrix.f + box.y + box.height};
        });
        const shifts = [0];
        for (let index = 1; index < stages.length; index++) {
          const gap = stages[index].top - stages[index - 1].bottom;
          if (gap < 44) throw Error('Stage spacing must support a 44px connector corridor');
          shifts.push(shifts[index - 1] + gap - 44);
        }
        const tones = [
          {fill: '#f2f5f8', border: '#ccd7e0', stripe: '#738ca1', title: '#546d82'},
          {fill: '#fafafa', border: '#dedfe2', stripe: '#717780', title: '#b96725'},
          {fill: '#f2f6f3', border: '#cedbd2', stripe: '#7b9c88', title: '#587563'},
        ];
        const stageFor = y => stages.reduce((best, stage, index) =>
          Math.abs(y - stage.center) < Math.abs(y - stages[best].center) ? index : best, 0);
        const connectors = [...element.querySelectorAll('path[marker-end]')];
        if (source.includes('-->') && connectors.length !== 2) throw Error('Expected two stage connectors');
        for (const connector of connectors) {
          const start = connector.getPointAtLength(0);
          const end = connector.getPointAtLength(connector.getTotalLength());
          const firstStage = stageFor(start.y), lastStage = stageFor(end.y);
          connector.setAttribute('d', `M${start.x},${start.y - shifts[firstStage]} L${end.x},${end.y - shifts[lastStage]}`);
          connector.setAttribute('data-stage-connector', 'true');
          connector.style.stroke = '#9aabb7';
          connector.style.strokeWidth = '1.8px';
          const length = connector.getTotalLength();
          if (length < 36 || length > 48) throw Error(`Unexpected connector length: ${length}`);
        }
        for (const node of element.querySelectorAll('.node')) {
          const matrix = node.transform.baseVal.consolidate().matrix;
          const stageIndex = stageFor(matrix.f);
          matrix.f -= shifts[stageIndex];
          node.transform.baseVal.initialize(element.createSVGTransformFromMatrix(matrix));
          const tone = tones[stageIndex];
          const rectangle = node.querySelector('rect');
          const text = node.querySelector('text');
          if (!rectangle || !text || node.classList.contains('container')) continue;
          if (node.classList.contains('section')) {
            for (const part of text.querySelectorAll('.text-inner-tspan')) part.setAttribute('font-weight', '700');
            text.style.setProperty('fill', tone.title, 'important');
            continue;
          }
          if (node.classList.contains('neutral')) {
            rectangle.style.setProperty('fill', tone.fill, 'important');
            rectangle.style.setProperty('stroke', tone.border, 'important');
          }
          const first = text.querySelector('.text-outer-tspan');
          if (first) {
            first.style.fontWeight = '700';
            for (const part of first.querySelectorAll('.text-inner-tspan')) part.setAttribute('font-weight', '700');
          }
          for (const row of [...text.querySelectorAll('.text-outer-tspan')].slice(1)) row.style.fill = '#4f5660';
          const stripe = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
          stripe.setAttribute('x', Number(rectangle.getAttribute('x')) + 7);
          stripe.setAttribute('y', Number(rectangle.getAttribute('y')) + 14);
          stripe.setAttribute('width', '3');
          stripe.setAttribute('height', Math.max(12, Number(rectangle.getAttribute('height')) - 28));
          stripe.setAttribute('rx', '1.5');
          const accent = node.classList.contains('accent') ? '#e86f00' : node.classList.contains('success') ? '#35775a' : node.classList.contains('failure') ? '#b65454' : tone.stripe;
          stripe.setAttribute('style', `fill:${accent}!important;stroke:none!important`);
          node.insertBefore(stripe, node.querySelector('.label'));
          rectangle.setAttribute('rx', '10');
          rectangle.setAttribute('ry', '10');
        }
        const view = element.viewBox.baseVal;
        const height = view.height - shifts.at(-1);
        element.setAttribute('viewBox', `${view.x} ${view.y} ${view.width} ${height}`);
        element.setAttribute('height', height);
      }
      for (const text of element.querySelectorAll('.edgeLabel text')) {
        const box = text.getBBox();
        const parent = text.parentElement;
        let background = parent.querySelector(':scope > rect.background');
        if (!background) {
          background = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
          parent.insertBefore(background, text);
        }
        background.setAttribute('data-label-background', 'true');
        background.setAttribute('x', box.x - 6);
        background.setAttribute('y', box.y - 6);
        background.setAttribute('width', box.width + 12);
        background.setAttribute('height', box.height + 12);
        background.setAttribute('rx', '3');
        background.setAttribute('style', 'fill:#ffffff!important;fill-opacity:1;opacity:1;stroke:none');
      }
      const titleLayer = document.createElementNS('http://www.w3.org/2000/svg', 'g');
      titleLayer.setAttribute('data-title-layer', 'true');
      for (const label of element.querySelectorAll('.cluster-label')) {
        const text = label.querySelector('text');
        if (!text) throw Error('Cluster title must use SVG text');
        const box = text.getBBox();
        const fill = getComputedStyle(label.closest('.cluster').querySelector('rect')).fill;
        const background = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        background.setAttribute('x', box.x - 6);
        background.setAttribute('y', box.y - 6);
        background.setAttribute('width', box.width + 12);
        background.setAttribute('height', box.height + 12);
        background.setAttribute('style', `fill:${fill};stroke:none;opacity:1;fill-opacity:1`);
        text.parentElement.insertBefore(background, text);
        const matrix = element.getScreenCTM().inverse().multiply(label.getScreenCTM());
        label.setAttribute('transform', `matrix(${matrix.a},${matrix.b},${matrix.c},${matrix.d},${matrix.e},${matrix.f})`);
        titleLayer.appendChild(label);
      }
      element.appendChild(titleLayer);
      const namespace = 'http://www.w3.org/2000/svg';
      const canvas = document.createElementNS(namespace, 'svg');
      const width = Math.max(900, element.viewBox.baseVal.width + 64);
      const height = element.viewBox.baseVal.height + 174;
      canvas.setAttribute('xmlns', namespace);
      canvas.setAttribute('width', width);
      canvas.setAttribute('height', height);
      canvas.setAttribute('viewBox', `0 0 ${width} ${height}`);
      const add = (tag, attributes, text) => {
        const item = document.createElementNS(namespace, tag);
        for (const [key, value] of Object.entries(attributes)) item.setAttribute(key, value);
        if (text) item.textContent = text;
        canvas.appendChild(item);
        return item;
      };
      const label = (x, y, size, color, weight, text) => add('text', {x, y, 'font-family': 'Microsoft YaHei', 'font-size': size, fill: color, 'font-weight': weight}, text);
      add('rect', {width, height, fill: '#ffffff'});
      label(32, 25, 13, '#e86f00', 700, 'PRISM / 技术文档');
      label(32, 62, 28, '#202124', 700, description[0]);
      label(32, 91, 16, '#717780', 400, description[1]);
      add('line', {x1: 32, y1: 108, x2: width - 32, y2: 108, stroke: '#dedfe2'});
      add('line', {x1: 32, y1: 108, x2: 100, y2: 108, stroke: '#e86f00', 'stroke-width': 3});
      element.setAttribute('x', (width - element.viewBox.baseVal.width) / 2);
      element.setAttribute('y', 126);
      canvas.appendChild(element);
      add('line', {x1: 32, y1: height - 34, x2: width - 32, y2: height - 34, stroke: '#dedfe2'});
      const legend = source.includes('-->') ? '蓝灰：输入    橙色：处理    浅绿：结果' : '辅助色：资料分组    橙色：关键条件';
      label(32, height - 12, 13, '#717780', 400, legend);
      const note = source.includes('-->') ? '箭头表示阶段衔接，同行模块按说明协作' : '各行按资料类别组织，关联条件见模块说明';
      label(width - 32, height - 12, 13, '#717780', 400, note).setAttribute('text-anchor', 'end');
      document.querySelector('#figure').replaceChildren(canvas);
      const missingNodes = [...element.querySelectorAll('.node')].filter(node => !node.classList.contains('container') && node.querySelector('.label') && !node.textContent.trim()).map(node => ({id: node.id, className: node.getAttribute('class')}));
      return {svg: new XMLSerializer().serializeToString(canvas), missingLabels: missingNodes.length, missingNodes,
        width, height};
    }, {source: source + blockStyles, description: descriptions[name]});
    assert.equal(result.missingLabels, 0, JSON.stringify(result.missingNodes));
    await saveArtifact(path.join(folder, name + '.svg'), result.svg);
    await saveArtifact(path.join(folder, name + '.png'), await page.locator('#figure').screenshot());
    console.log(JSON.stringify({name, width: result.width, height: result.height}));
  }
} finally {
  await browser.close();
  await new Promise(resolve => server.close(resolve));
}

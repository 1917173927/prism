import { Graph } from '@antv/x6';
import { workflowStages, workflowDraftKey } from './workflow-stages.src.js';

const element = id => document.getElementById(id);
let graph = null, loaded = null, generation = 0, busy = false;
let view = 'pipeline', runStates = new Map();
const owner = () => element('owner-id').value.trim();
const status = message => { element('workflow-status').textContent = message; };
const roleNames = {MACRO:'宏观', INDUSTRY:'行业', STOCK:'个股', ETF_FUND:'基金'};

function draftNodes() {
  return graph.getNodes().map(node => ({node_id:node.id, ...node.position(),
    dependencies:graph.getIncomingEdges(node)?.map(edge => edge.getSourceCellId()).sort() || []}));
}

function renderPipeline() {
  const panel = element('workflow-pipeline');
  panel.replaceChildren();
  if (!graph || !loaded) {panel.textContent = '请先读取工作流。'; return;}
  const {stages, unresolved} = workflowStages(draftNodes());
  const labels = new Map(loaded.catalog.map((item, i) => [item.node_id, `${roleNames[item.role] || item.role} · 来源 ${i % 2 + 1}`]));
  for (const [index, nodes] of stages.entries()) {
    const section = document.createElement('section');
    const title = document.createElement('h4');
    title.textContent = `阶段 ${index + 1} · ${nodes.length} 个可并行节点`;
    section.append(title);
    for (const node of nodes) {
      const card = document.createElement('article'); card.className = 'context-memory-card';
      const heading = document.createElement('strong'); heading.textContent = labels.get(node.node_id);
      const deps = document.createElement('p');
      deps.textContent = node.dependencies.length ? `等待：${node.dependencies.map(id => labels.get(id) || id).join('、')}` : '无前置依赖';
      const result = document.createElement('span'); result.className = 'status-chip';
      const run = runStates.get(node.node_id);
      result.textContent = run ? `${run.status} · 尝试 ${run.attempt} 次` : 'NOT_RUN';
      card.append(heading, deps, result); section.append(card);
    }
    panel.append(section);
  }
  if (unresolved.length) {
    const warning = document.createElement('p');
    warning.textContent = `BLOCKED · ${unresolved.length} 个节点存在环路或未知依赖，请修正后保存。`;
    panel.append(warning);
  }
}

function switchView(next) {
  view = next;
  element('workflow-canvas-wrap').hidden = view !== 'canvas';
  element('workflow-pipeline').hidden = view !== 'pipeline';
  element('workflow-view-canvas').setAttribute('aria-pressed', String(view === 'canvas'));
  element('workflow-view-pipeline').setAttribute('aria-pressed', String(view === 'pipeline'));
  renderPipeline();
}

function edited(message) {
  runStates.clear(); element('workflow-result').textContent = '';
  renderPipeline(); status(message);
}

async function request(path, body) {
  const response = await fetch(`/api/v1/advisor/${path}`, {
    method:body ? 'POST' : 'GET', headers:{'X-Owner-ID':owner(), 'Content-Type':'application/json'},
    ...(body ? {body:JSON.stringify(body)} : {}),
  });
  const data = await response.json();
  if (!response.ok) throw Error(data.message || `请求失败 ${response.status}`);
  return data;
}

async function action(callback) {
  if (busy) return;
  busy = true;
  for (const id of ['workflow-load','workflow-save','workflow-run','workflow-add-edge','workflow-remove-edge']) element(id).disabled = true;
  try { await callback(); } catch (error) { status(error.message); }
  finally {
    busy = false;
    for (const id of ['workflow-load','workflow-save','workflow-run','workflow-add-edge','workflow-remove-edge']) element(id).disabled = false;
  }
}

function render(data) {
  if (graph) graph.dispose();
  graph = new Graph({container:element('workflow-canvas'), width:1000, height:390,
    translating:{restrict:true},
    grid:true, background:{color:'#faf9f6'}, connecting:{allowBlank:false, allowLoop:false, allowMulti:false}});
  for (const id of ['workflow-source','workflow-target']) element(id).replaceChildren();
  const labels = new Map(data.catalog.map((item, i) => [item.node_id, `${roleNames[item.role] || item.role} · 来源 ${i % 2 + 1}`]));
  for (const item of data.definition.nodes) {
    graph.addNode({id:item.node_id, x:item.x, y:item.y, width:200, height:65, label:labels.get(item.node_id),
      attrs:{body:{fill:'#fff',stroke:'#687967',rx:8,ry:8},label:{fill:'#26362b',fontSize:14}}});
    for (const id of ['workflow-source','workflow-target']) {
      const option = document.createElement('option'); option.value = item.node_id; option.textContent = labels.get(item.node_id);
      element(id).append(option);
    }
  }
  for (const item of data.definition.nodes) for (const dependency of item.dependencies) graph.addEdge({source:dependency, target:item.node_id});
  graph.on('node:moved', () => edited('位置已调整；请保存新版本'));
  graph.on('edge:dblclick', ({edge}) => { if (!busy) {graph.removeCell(edge); edited('依赖已移除；请保存新版本');} });
  runStates.clear(); switchView(view);
}

async function load() {
  const current = ++generation, requestOwner = owner();
  const data = await request('workflow');
  if (current !== generation || owner() !== requestOwner) return;
  loaded = data;
  render(data);
  element('workflow-result').textContent = '';
  status(`MOCK · 第 ${data.revision} 版 · ${data.boundary}`);
}

function requireOwner() {
  if (!loaded || loaded.definition.owner_id !== owner()) throw Error('请先读取当前账户的工作流');
}

async function save() {
  requireOwner();
  const definition = {...loaded.definition, nodes:draftNodes()};
  const requestOwner = owner();
  const saved = await request('workflow', {definition, expected_revision:loaded.revision});
  if (owner() !== requestOwner) return;
  loaded = {...loaded, ...saved};
  status(`已保存 · 第 ${saved.revision} 版 · MOCK`);
}

async function run() {
  requireOwner();
  if (!loaded.revision) throw Error('请先保存工作流');
  const requestOwner = owner(), revision = loaded.revision;
  // Prevent showing saved-run states on a different, unsaved topology.
  if (workflowDraftKey(draftNodes()) !== workflowDraftKey(loaded.definition.nodes)) {
    throw Error('请先保存或重新读取工作流，再运行当前视图对应的版本');
  }
  runStates.clear(); element('workflow-result').textContent = ''; renderPipeline();
  status(`正在运行已保存第 ${revision} 版；画布未保存改动不参与运行`);
  const output = await request('workflow-runs', {expected_revision:revision});
  if (owner() !== requestOwner) return;
  runStates = new Map(output.result.execution.state.nodes.map(node => [node.node_id, node]));
  renderPipeline();
  status(`MOCK · 第 ${revision} 版 · ${output.result.execution.state.status}`);
  element('workflow-result').textContent = output.result.execution.state.nodes.map(node =>
    `${node.node_id}: ${node.status} · 尝试 ${node.attempt} 次`).join('\n') + '\n结果只用于合成数据编排演练，不是投资建议。';
}

function edge(add) {
  requireOwner();
  const source = element('workflow-source').value, target = element('workflow-target').value;
  if (source === target) throw Error('节点不能依赖自身');
  const existing = graph.getEdges().find(item => item.getSourceCellId() === source && item.getTargetCellId() === target);
  if (add && !existing) graph.addEdge({source,target});
  if (!add && existing) graph.removeCell(existing);
  edited('依赖已调整；保存时由服务端校验环路');
}

element('workflow-load').addEventListener('click', () => action(load));
element('workflow-save').addEventListener('click', () => action(save));
element('workflow-run').addEventListener('click', () => action(run));
element('workflow-add-edge').addEventListener('click', () => action(() => edge(true)));
element('workflow-remove-edge').addEventListener('click', () => action(() => edge(false)));
element('workflow-view-canvas').addEventListener('click', () => switchView('canvas'));
element('workflow-view-pipeline').addEventListener('click', () => switchView('pipeline'));
window.addEventListener('pagehide', () => { if (graph) graph.dispose(); graph = null; });

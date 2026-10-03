"""Behavior checks for the isolated, local-only product presentation."""

import json
from html.parser import HTMLParser
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "app/api/static/demos/product-demo"


HARNESS = r"""
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const routes = ['copilot','overview','market','trading-style','profile','skill-store','research-knowledge','live-research','research-algorithms'];
const toCamel = key => key.replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
const events = new Map(), windowEvents = new Map(), timers = new Map(), frames = new Map();
let serial = 0, networkCalls = 0, chartRemoved = 0;
const observers = [], createdCharts = [];
class Element {
  constructor(tag='div', attrs={}) {
    this.tagName=tag.toUpperCase(); this.children=[]; this.parentElement=null;
    this.dataset={}; this.attributes={}; this.style={}; this.hidden=false;
    this.disabled=false; this.value=''; this._text=''; this.classes=new Set();
    this.clientWidth=500; this.clientHeight=200;
    this.classList={
      add: (...names) => names.forEach(name=>this.classes.add(name)),
      remove: (...names) => names.forEach(name=>this.classes.delete(name)),
      contains: name=>this.classes.has(name),
      toggle: (name, force) => { const result=force===undefined?!this.classes.has(name):force; result?this.classes.add(name):this.classes.delete(name); return result; },
    };
    Object.entries(attrs).forEach(([key,value])=>this.setAttribute(key,value));
  }
  set className(value){this.classes=new Set(value.split(/\s+/).filter(Boolean));}
  get className(){return [...this.classes].join(' ');}
  set textContent(value){this._text=String(value);this.children=[];}
  get textContent(){return this._text+this.children.map(child=>child.textContent).join('');}
  get lastElementChild(){return this.children[this.children.length-1];}
  get isConnected(){return this===document.body||!!this.parentElement?.isConnected;}
  append(...nodes){nodes.forEach(node=>{node.parentElement=this;this.children.push(node);});}
  replaceChildren(...nodes){this.children.forEach(node=>node.parentElement=null);this.children=[];this._text='';this.append(...nodes);}
  setAttribute(name,value){this.attributes[name]=String(value);if(name.startsWith('data-'))this.dataset[toCamel(name.slice(5))]=String(value);if(name==='id')this.id=String(value);}
  removeAttribute(name){delete this.attributes[name];}
  getAttribute(name){return this.attributes[name]??null;}
  focus(){document.activeElement=this;}
  matches(selector){
    return selector.split(',').some(raw=>{
      const part=raw.trim();
      if(part.startsWith('#'))return this.id===part.slice(1);
      const attribute=part.match(/^(?:([a-z]+))?\[([\w-]+)(?:="([^"]*)")?\]$/);
      if(attribute){const[,tag,name,value]=attribute;const actual=name.startsWith('data-')?this.dataset[toCamel(name.slice(5))]:this.attributes[name];return(!tag||this.tagName===tag.toUpperCase())&&actual!==undefined&&(value===undefined||actual===value);}
      return this.tagName===part.toUpperCase();
    });
  }
  closest(selector){return this.matches(selector)?this:this.parentElement?.closest(selector)||null;}
  querySelectorAll(selector){return this.children.flatMap(child=>[...(child.matches(selector)?[child]:[]),...child.querySelectorAll(selector)]);}
  querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
}
const document={body:new Element('body'),activeElement:null,title:'',createElement:tag=>new Element(tag),
  querySelectorAll(selector){return this.body.querySelectorAll(selector);},
  querySelector(selector){return this.body.querySelector(selector);},
  addEventListener(type,callback){if(!events.has(type))events.set(type,[]);events.get(type).push(callback);},
};
const add=(tag,attrs={},parent=document.body)=>{const node=new Element(tag,attrs);parent.append(node);return node;};
routes.forEach(id=>{const page=add('section',{'data-page':id});add('h1',{'data-page-title':id},page).textContent=id;add('a',{'data-nav':id});if(['overview','market','research-algorithms'].includes(id))add('div',{'data-chart':id==='overview'?'portfolio':id==='market'?'market':'regime'},page);});
const lists=['allocation','market-quotes','market-metrics','market-sectors','trading-metrics','trading-style','profile-dimensions','factor-missing','skills','documents','copilot','copilot-presets','tools','live-steps','live-result'];
lists.forEach(name=>add('div',{'data-list':name}));
['holdings','trades','covariance'].forEach(name=>add('tbody',{'data-table':name}));
['summary','questionnaire','preferences'].forEach(name=>{add('button',{'data-profile-tab':name});add('div',{'data-profile-panel':name});});
['daily','monthly'].forEach(name=>add('button',{'data-market-period':name}));
['*','市场数据','公司研究'].forEach(name=>add('button',{'data-skill-category':name}));
['menu-toggle','capture-toggle','reset','live-start','live-cancel'].forEach(name=>add('button',{'data-action':name}));
const captureIcon=add('button',{'data-action':'capture-toggle'});captureIcon.className='icon-button';add('svg',{},captureIcon);
add('select',{'data-page-menu':''});add('strong',{'data-page-name':''});
['skills','knowledge'].forEach(name=>add('input',{'data-search':name}));
add('textarea',{'data-input':'copilot'});
['copilot','knowledge'].forEach(name=>add('form',{'data-form':name}));
add('div',{'data-live-status':''});add('div',{'data-live-timing':''});add('div',{'data-skill-count':''});add('div',{'data-knowledge-count':''});
add('select',{'data-preference':'detail','data-default':'standard'});add('p',{'data-preference-output':''});
add('span',{'data-value':'portfolio.total_cny'});add('span',{'data-value':'market.active.name'});add('span',{'data-value':'not.provided'});
const algorithmStatus=add('span',{'data-value':'algorithms.covariance.status'});algorithmStatus.className='status pass';
const algorithmReason=add('p',{'data-algorithm-reason':'covariance'});algorithmReason.hidden=true;
const drawer=add('aside',{id:'citation-drawer'});drawer.hidden=true;
add('button',{'data-action':'citation-close'},drawer);
['title','excerpt','source','meta'].forEach(name=>add('p',{'data-citation':name},drawer));
let url=new URL('http://localhost/demo/?capture=1#unknown');
const location={};['href','hash','search','pathname'].forEach(name=>Object.defineProperty(location,name,{get:()=>url[name],set:value=>{url[name]=value;}}));
const window={document,location,scrollY:0,history:{replaceState(_state,_title,value){url=new URL(value,url);}},
  addEventListener(type,callback){if(!windowEvents.has(type))windowEvents.set(type,[]);windowEvents.get(type).push(callback);},
  setTimeout(callback){const id=++serial;timers.set(id,callback);return id;},clearTimeout:id=>timers.delete(id),
  requestAnimationFrame(callback){const id=++serial;frames.set(id,callback);return id;},cancelAnimationFrame:id=>frames.delete(id),
  scrollTo(options){this.scrollY=options.top;},
  getComputedStyle(){return{getPropertyValue(name){return({'--brand':'#ab6100','--market-up':'#e14444','--market-down':'#168471'})[name]||'';}};},
};
window.ResizeObserver=class{constructor(callback){this.callback=callback;this.connected=false;observers.push(this);}observe(){this.connected=true;}disconnect(){this.connected=false;}};
window.LightweightCharts={CandlestickSeries:'candle',HistogramSeries:'histogram',AreaSeries:'area',
  createChart(container){const chart={container,removed:false,series:[],addSeries(type,options){const series={type,options,setData(value){this.data=value;}};this.series.push(series);return series;},panes(){return[{setHeight(){}},{setHeight(){}}];},timeScale(){return{fitContent(){}};},applyOptions(){assert.equal(this.removed,false);},remove(){assert.equal(this.removed,false);this.removed=true;chartRemoved++;}};createdCharts.push(chart);return chart;},
};
const forbidden=()=>{networkCalls++;throw Error('Demo accessed a remote or persisted resource');};
window.fetch=forbidden;window.XMLHttpRequest=forbidden;window.WebSocket=forbidden;
Object.defineProperty(window,'localStorage',{get:forbidden});Object.defineProperty(window,'sessionStorage',{get:forbidden});
const context=vm.createContext({window,document,URL,URLSearchParams,console,fetch:forbidden,XMLHttpRequest:forbidden,WebSocket:forbidden});
vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context);
const unavailable=process.argv[3]==='unavailable';
if(unavailable){const covariance=window.PRISM_DEMO_DATA.algorithms.covariance;covariance.status='UNAVAILABLE';covariance.reason='共同有效收益不足，无法计算';covariance.shrinkage='不可计算';covariance.matrix=[];covariance.matrix_display=[];}
const snapshot=JSON.stringify(window.PRISM_DEMO_DATA);
vm.runInContext(fs.readFileSync(process.argv[2],'utf8'),context);
const get=selector=>document.querySelector(selector);
const emit=(type,target,extra={})=>(events.get(type)||[]).forEach(callback=>callback({target,preventDefault(){},...extra}));
const emitWindow=type=>(windowEvents.get(type)||[]).forEach(callback=>callback({}));
const click=selector=>emit('click',typeof selector==='string'?get(selector):selector);
const flushFrames=()=>{const queued=[...frames.values()];frames.clear();queued.forEach(callback=>callback());};
const route=id=>{location.hash=id;emitWindow('hashchange');flushFrames();};
const tick=()=>{const queued=[...timers.values()];timers.clear();queued.forEach(callback=>callback());};
const findings={};

assert.equal(location.hash,'#copilot');assert.equal(get('[data-page="copilot"]').hidden,false);
assert.equal(get('[data-value="not.provided"]').textContent,'未提供');
assert.equal(document.body.classList.contains('capture-mode'),true);
assert.equal(captureIcon.children[0].tagName,'SVG');assert.equal(captureIcon.getAttribute('aria-label'),'退出截图模式');
assert.equal(get('[data-page-menu]').value,'copilot');assert.equal(get('[data-page-name]').textContent,'copilot');
assert.equal(Object.isFrozen(window.PRISM_DEMO_DATA.portfolio),true);
assert.equal(algorithmStatus.classList.contains('pass'),!unavailable);assert.equal(algorithmStatus.classList.contains('warning'),unavailable);
assert.equal(algorithmStatus.textContent,unavailable?'暂无法分析':'已计算');
assert.equal(algorithmReason.hidden,!unavailable);if(unavailable)assert.equal(algorithmReason.textContent,'共同有效收益不足，无法计算');
route('market');assert.equal(createdCharts.length,1);assert.equal(observers.filter(observer=>observer.connected).length,1);
assert.equal(createdCharts[0].series[0].options.upColor,'#e14444');
click('[data-action="menu-toggle"]');assert.equal(document.body.classList.contains('nav-open'),true);
click('[data-nav="market"]');assert.equal(document.body.classList.contains('nav-open'),false);
click('[data-market-period="monthly"]');flushFrames();assert.equal(chartRemoved,1);
observers[0].callback([{contentRect:{width:600}}]);
assert.equal(createdCharts.at(-1).series[0].data,window.PRISM_DEMO_DATA.market.instruments.shanghai.monthly);
click(get('[data-market-instrument="shenzhen"]'));flushFrames();
assert.equal(get('[data-list="market-metrics"]').children[0].children[1].textContent,window.PRISM_DEMO_DATA.market.instruments.shenzhen.metrics[0].value);
click(get('[data-market-instrument="shanghai"]'));flushFrames();
window.scrollY=312;route('overview');assert.equal(chartRemoved,4);assert.equal(createdCharts.at(-1).series[0].options.lineColor,'#ab6100');route('market');assert.equal(window.scrollY,312);
findings.routing_and_chart_cleanup=true;

route('live-research');click('[data-action="live-start"]');assert.equal(timers.size,1);
assert.equal(get('[data-live-status]').textContent,'演示进行中');
click('[data-action="live-cancel"]');assert.equal(timers.size,0);tick();assert.equal(get('[data-live-status]').textContent,'已取消');
click('[data-action="live-start"]');route('copilot');assert.equal(timers.size,0);
assert.equal(get('[data-live-status]').textContent,'已取消');
route('live-research');click('[data-action="live-start"]');
for(let index=0;index<window.PRISM_DEMO_DATA.live.steps.length;index++)tick();
assert.equal(get('[data-live-status]').textContent,'演示已完成');assert.equal(timers.size,0);
assert.equal(get('[data-list="live-result"]').children.length,window.PRISM_DEMO_DATA.live.result.length);
findings.live_cancel_and_completion=true;

route('copilot');const input=get('[data-input="copilot"]');input.value='<img src=x onerror="fetch(1)">';emit('submit',get('[data-form="copilot"]'));
assert.ok(get('[data-list="copilot"]').textContent.includes(input.value));
assert.ok(get('[data-list="copilot"]').textContent.includes('演示样例未覆盖'));
assert.equal(get('[data-list="copilot"]').querySelectorAll('img').length,0);
input.value=window.PRISM_DEMO_DATA.copilot.presets[0].query;emit('submit',get('[data-form="copilot"]'));
const citation=get('[data-citation="doc-portfolio"]');click(citation);assert.equal(drawer.hidden,false);
assert.ok(get('[data-citation="meta"]').textContent.includes('演示资料'));emit('keydown',document.body,{key:'Escape'});
assert.equal(drawer.hidden,true);assert.equal(document.activeElement,citation);
assert.equal(document.body.classList.contains('capture-mode'),true);
emit('keydown',document.body,{key:'Escape'});assert.equal(document.body.classList.contains('capture-mode'),false);assert.equal(new URLSearchParams(location.search).has('capture'),false);
findings.uncovered_query_xss_and_citation=true;

route('skill-store');const skill=window.PRISM_DEMO_DATA.skills[0];const original=skill.selected;
click(`[data-skill-toggle="${skill.id}"]`);assert.equal(get(`[data-skill-toggle="${skill.id}"]`).getAttribute('aria-pressed'),String(!original));
assert.equal(document.activeElement,get(`[data-skill-toggle="${skill.id}"]`));
assert.equal(skill.selected,original);get('[data-search="skills"]').value='no matching skill';emit('input',get('[data-search="skills"]'));
assert.ok(get('[data-list="skills"]').textContent.includes('没有匹配'));
route('profile');emit('keydown',get('[data-profile-tab="summary"]'),{key:'ArrowRight'});
assert.equal(get('[data-profile-panel="questionnaire"]').hidden,false);assert.equal(document.activeElement,get('[data-profile-tab="questionnaire"]'));
get('[data-preference="detail"]').value='concise';emit('change',get('[data-preference="detail"]'));assert.ok(get('[data-preference-output]').textContent.startsWith('简洁解释'));
get('[data-page-menu]').value='research-knowledge';emit('change',get('[data-page-menu]'));emitWindow('hashchange');assert.equal(get('[data-page="research-knowledge"]').hidden,false);
route('research-knowledge');get('[data-search="knowledge"]').value='no matching document';emit('submit',get('[data-form="knowledge"]'));
assert.ok(get('[data-list="documents"]').textContent.includes('未找到匹配'));
click('[data-action="reset"]');emitWindow('hashchange');flushFrames();assert.equal(location.hash,'#copilot');
assert.equal(get(`[data-skill-toggle="${skill.id}"]`).getAttribute('aria-pressed'),String(original));
assert.equal(get('[data-search="knowledge"]').value,'');assert.equal(get('[data-live-status]').textContent,'待开始');
assert.equal(JSON.stringify(window.PRISM_DEMO_DATA),snapshot);
findings.search_and_reset_preserve_snapshot=true;

route('research-algorithms');
assert.equal(createdCharts.at(-1).series[0].data,window.PRISM_DEMO_DATA.algorithms.regime.display_series);
assert.equal(createdCharts.at(-1).series[0].options.priceFormat.type,'percent');
assert.deepEqual(JSON.parse(JSON.stringify(createdCharts.at(-1).series[0].options.autoscaleInfoProvider())),{priceRange:{minValue:0,maxValue:100}});
route('market');assert.equal(observers.filter(observer=>observer.connected).length,1);
emitWindow('pagehide');assert.equal(observers.filter(observer=>observer.connected).length,0);assert.equal(frames.size,0);assert.equal(timers.size,0);
assert.equal(networkCalls,0);
findings.pagehide_and_no_external_resources=true;
console.log(JSON.stringify(findings));
"""


@pytest.mark.parametrize("algorithm_status", ["calculated", "unavailable"])
def test_product_demo_navigation_cancel_isolation_and_safe_rendering(algorithm_status):
    """Exercise real event handlers and resource ownership with a observable DOM."""
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required for the standalone presentation runtime")
    result = subprocess.run(
        [node, "-e", HARNESS, str(DEMO / "data.js"), str(DEMO / "demo.js"), algorithm_status],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
    )
    findings = json.loads(result.stdout)
    assert findings == {
        "routing_and_chart_cleanup": True,
        "live_cancel_and_completion": True,
        "uncovered_query_xss_and_citation": True,
        "search_and_reset_preserve_snapshot": True,
        "pagehide_and_no_external_resources": True,
    }


def test_product_demo_html_uses_snapshot_fields_and_local_controls():
    """Check the actual presentation markup against its immutable data contract."""
    class Markup(HTMLParser):
        def __init__(self):
            super().__init__()
            self.nodes = []

        def handle_starttag(self, tag, attributes):
            self.nodes.append((tag, dict(attributes)))

    markup = Markup()
    markup.feed((DEMO / "index.html").read_text(encoding="utf-8"))
    raw = (DEMO / "data.js").read_text(encoding="utf-8")
    snapshot = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
    routes = {
        "copilot", "overview", "market", "trading-style", "profile", "skill-store",
        "research-knowledge", "live-research", "research-algorithms",
    }
    pages = [attrs["data-page"] for _, attrs in markup.nodes if "data-page" in attrs]
    assert len(pages) == len(routes) and set(pages) == routes
    assert {attrs["data-nav"] for _, attrs in markup.nodes if "data-nav" in attrs} == routes
    assert {attrs["data-chart"] for _, attrs in markup.nodes if "data-chart" in attrs} == {"portfolio", "market", "regime"}
    forms = {attrs["data-form"] for _, attrs in markup.nodes if "data-form" in attrs}
    assert forms == {"copilot", "knowledge"}
    categories = {attrs["data-skill-category"] for _, attrs in markup.nodes if "data-skill-category" in attrs}
    assert {skill["category"] for skill in snapshot["skills"]} <= categories
    for _, attrs in markup.nodes:
        path = attrs.get("data-value")
        if path:
            if path.startswith("market.active."):
                value = snapshot["market"]["instruments"]["shanghai"]
                parts = path.split(".")[2:]
            else:
                value, parts = snapshot, path.split(".")
            for part in parts:
                assert isinstance(value, dict) and part in value, f"Missing snapshot field: {path}"
                value = value[part]
        for attribute in ("src", "href"):
            target = attrs.get(attribute)
            if not target or target.startswith("#"):
                continue
            assert not target.startswith(("http:", "https:", "//")), target
            assert (DEMO / target.split("?", 1)[0]).resolve().is_file(), target
    drawers = [(tag, attrs) for tag, attrs in markup.nodes if attrs.get("id") == "citation-drawer"]
    assert len(drawers) == 1
    assert drawers[0][0] == "aside" and drawers[0][1].get("role") == "dialog"
    assert "hidden" in drawers[0][1]

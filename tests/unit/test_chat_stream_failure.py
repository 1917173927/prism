from pathlib import Path
import re
import shutil
import subprocess

import pytest


def test_clear_context_aborts_active_turn_and_preserves_non_chat_settings():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js required")
    source = Path("app/api/static/app.js").read_text(encoding="utf-8")
    function = re.search(
        r"  function clearConversationContext\(\) \{[\s\S]*?\n  \}", source
    ).group()
    probe = r'''
const assert = require('node:assert/strict');
class Element {
  constructor(){this.children=['old'];this.value='query';this.hidden=false;this.style={};}
  replaceChildren(...items){this.children=items;}
}
const nodes=new Map();
const byId=id=>{if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id);};
let abortCount=0;
const activeChatController={abort:()=>abortCount++};
let chatContextRevision=0;
const chatHistory=[{role:'user',content:'old'}];
const chatSessions=[{id:'old-session',title:'旧对话',messages:[...chatHistory]}];
let activeChatSessionId='old-session';
const CHAT_SESSION_LIMIT=12;
const CHAT_LEGACY_STORAGE_KEY='prism_copilot_chat_history_v2';
const activeChatSession=()=>chatSessions.find(session=>session.id===activeChatSessionId)||null;
const createChatSessionRecord=()=>({id:'new-session',title:'新对话',messages:[]});
const storage=new Map([
  ['owner:chat','history'],
  ['owner:model','model-secret-reference'],
  ['owner:portfolio','portfolio-snapshot'],
]);
const workspaceStorage={removeItem:key=>storage.delete(key)};
const ownerStorageKey=key=>key===CHAT_LEGACY_STORAGE_KEY?'owner:chat':`owner:${key}`;
const clear=node=>{node.children=[];};
const renderChatWelcome=()=>byId('copilot-chat-messages').children.push('welcome');
const renderActiveChatMessages=()=>{clear(byId('copilot-chat-messages'));renderChatWelcome();byId('copilot-chat-panel').style.display='block';};
const renderChatSessionList=()=>{};
const persistChatSessions=()=>{};
const setAgentFeatureToolsCompact=()=>{};
const setError=()=>{};
const createPersistedChatSession=async()=>{const session={id:'new-session',title:'新对话',messages:[]};chatSessions.push(session);activeChatSessionId=session.id;};
'''+function+r'''
clearConversationContext();
assert.equal(abortCount,1);
assert.equal(chatContextRevision,1);
assert.deepEqual(chatHistory,[]);
assert.equal(chatSessions.length,2);
assert.equal(activeChatSessionId,'new-session');
assert.equal(storage.has('owner:chat'),false);
assert.equal(storage.get('owner:model'),'model-secret-reference');
assert.equal(storage.get('owner:portfolio'),'portfolio-snapshot');
assert.equal(byId('copilot-natural-input').value,'');
assert.equal(byId('chat-send-progress').hidden,false);
assert.match(byId('chat-send-progress').textContent,/理解问题/);

assert.deepEqual(byId('copilot-chat-messages').children,['welcome']);
assert.deepEqual(byId('copilot-decision-output').children,[]);
assert.equal(byId('copilot-chat-panel').style.display,'block');
'''
    result = subprocess.run([node, "-e", probe], capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr


def test_frontend_stream_failure_is_visible_and_not_saved_as_completed_answer():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js required")
    source = Path("app/api/static/app.js").read_text(encoding="utf-8")
    function = re.search(r"  async function handleStreamingChat\([^\n]*\) \{[\s\S]*?\n  \}", source).group()
    function += "\n" + re.search(r"  async function performStreamingChat\([^\n]*\) \{[\s\S]*?\n  \}", source).group()
    function += "\n" + re.search(r"  async function readChatStreamChunk\([^\n]*\) \{[\s\S]*?\n  \}", source).group()
    function += "\n" + "\n".join(re.search(r"  function " + name + r"\([^\n]*\) \{[\s\S]*?\n  \}", source).group()
                                  for name in [
                                      "createLinkedTimeoutController",
                                      "completedHistoryForScope",
                                      "profileLevelText", "currentProfileTag", "activeProfileTag", "recordTruthTurnAlert",
                                  ])
    probe = r'''
const assert = require('node:assert/strict');
const CHAT_PRECHECK_TIMEOUT_MS = 8000;
const CHAT_STREAM_IDLE_TIMEOUT_MS = 15000;
class Element {
  constructor(){
    this.children=[]; this.style={}; this.value='';
    const states=new Set();
    this.classList={
      add:(...values)=>values.forEach(value=>states.add(value)),
      remove:(...values)=>values.forEach(value=>states.delete(value)),
      contains:value=>states.has(value),
    };
  }
  append(...items){this.children.push(...items);}
  remove(){}
  replaceChildren(...items){this.children=items;}
  addEventListener(){}
  set textContent(value){this.children=[String(value)];}
  get textContent(){return this.children.map(x=>typeof x==='string'?x:x.textContent).join(' ');}
}
let truthTurnCounter=0, activeChatController=null, chatContextRevision=0;
const clearChatEmptyState=()=>{};
const nodes=new Map();
const byId=id=>{if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id);};
const document={createElement:()=>new Element()};
const state={ownerId:'owner',selectedPersona:'custom-user',dataMode:'MOCK'};
const accountAccessEnabled=false;
const PERSONAS={}, DEFAULT_USER_PROFILE={}, llmConfig={}, chatHistory=[];
let activeChatSessionId='chat-server-session';
const createPersistedChatSession=async()=>{};
const refreshPersistedChatSessions=async()=>{};
let truthResult={revision:1,status:'LOCKED'};
let truthFailure=null;
const refreshSessionTruth=async()=>{if(truthFailure)throw truthFailure;return truthResult;};
const setError=message=>{throw Error(message);};
const saveCopilotChatHistory=()=>{};
const renderAssistantMarkdown=(node,text)=>{node.textContent=text;};
const buildPipelineStepItem=()=>new Element();
let completed=0;
const setPipelineStepState=(item,state)=>{if(state==='completed')completed++;};
let wire='';
let fetchCalls=0;
let lastFetchOptions=null;
const fetch=async(url,options)=>{fetchCalls++;lastFetchOptions=options;return new Response(new ReadableStream({start(controller){
  controller.enqueue(new TextEncoder().encode(wire));controller.close();
}}));};
'''+function+r'''
(async()=>{
 for(const [data,message] of [
  ['data: {"type":"error","message":"前提已变化"}\n\ndata: [DONE]\n\n','前提已变化'],
  ['', '结果不完整'],
 ]){
  wire=data.replaceAll('\\n','\n');
  // The Python raw string preserves JS newline escapes, evaluated by Node.
  nodes.clear();chatHistory.length=0;completed=0;
  await handleStreamingChat('检查当前前提');
  assert.match(byId('copilot-chat-messages').textContent,new RegExp(message));
  assert.equal(chatHistory.filter(x=>x.role==='assistant').length,0);
  assert.equal(completed,0);
  assert.match(byId('truth-turn-alerts').textContent,new RegExp(message));
 }
 truthResult={revision:2,status:'DRIFT_DETECTED'};
 wire='data: {"type":"token","delta":"通用回答"}\n\ndata: [DONE]\n\n'.replaceAll('\\n','\n');
 nodes.clear();chatHistory.length=0;completed=0;fetchCalls=0;
 await handleStreamingChat('不依赖持仓的一般问题');
 assert.equal(fetchCalls,1);
 const body=JSON.parse(lastFetchOptions.body);
 assert.equal(body.session_truth_id,null);
 assert.equal(body.profile_version,null);
 assert.equal(body.behavior_profile_version,null);
 assert.equal(body.portfolio_snapshot_id,null);
 assert.equal(body.persona_info,null);
 assert.deepEqual(body.history,[]);
 assert.match(byId('copilot-chat-messages').textContent,/通用回答/);
 assert.equal(chatHistory.filter(x=>x.role==='assistant').length,1);

 wire='data: {"type":"token","delta":"追问回答"}\n\ndata: [DONE]\n\n'.replaceAll('\\n','\n');
 await handleStreamingChat('那市净率呢');
 const followUpBody=JSON.parse(lastFetchOptions.body);
 assert.deepEqual(followUpBody.history,[
   {role:'user',content:'不依赖持仓的一般问题'},
   {role:'assistant',content:'通用回答'},
 ]);
 assert.equal(chatHistory.at(-1).content,'追问回答');

 for(const unavailableTruth of [null,'throw']){
  truthResult=unavailableTruth;truthFailure=unavailableTruth==='throw'?new Error('truth unavailable'):null;
  wire='data: {"type":"token","delta":"仍可回答"}\n\ndata: [DONE]\n\n'.replaceAll('\\n','\n');
  nodes.clear();chatHistory.length=0;completed=0;fetchCalls=0;
  await handleStreamingChat('一般问题');
  const unavailableBody=JSON.parse(lastFetchOptions.body);
  assert.equal(fetchCalls,1);
  assert.equal(unavailableBody.session_truth_id,null);
  assert.equal(unavailableBody.session_truth_revision,null);
 }

 truthResult={revision:1,status:'LOCKED'};
 truthFailure=null;
 wire='data: not-json\n\ndata: [DONE]\n\n'.replaceAll('\\n','\n');
 nodes.clear();chatHistory.length=0;completed=0;fetchCalls=0;
 await handleStreamingChat('异常流');
 assert.match(byId('copilot-chat-messages').textContent,/分析响应格式异常/);
 assert.equal(chatHistory.filter(x=>x.role==='assistant').length,0);
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
    result = subprocess.run([node, "-e", probe], capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr


def test_upstream_error_body_is_not_forwarded_to_browser(monkeypatch):
    import asyncio
    import httpx
    from app.llm.client import AsyncLLMClient, LLMConfig
    original = httpx.AsyncClient
    transport = httpx.MockTransport(lambda _: httpx.Response(401, json={"api_key":"private-test-value"}))
    monkeypatch.setattr("app.llm.client.httpx.AsyncClient", lambda **kwargs: original(transport=transport))
    async def collect():
        return [chunk async for chunk in AsyncLLMClient(LLMConfig(api_key="test-key", base_url="https://example.invalid")).stream_chat([])]
    chunks = asyncio.run(collect())
    assert chunks[0]["type"] == "error"
    assert "401" in chunks[0]["message"]
    assert "private-test-value" not in str(chunks)

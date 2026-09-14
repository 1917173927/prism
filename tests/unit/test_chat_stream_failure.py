from pathlib import Path
import re
import shutil
import subprocess

import pytest


def test_frontend_stream_failure_is_visible_and_not_saved_as_completed_answer():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js required")
    source = Path("app/api/static/app.js").read_text(encoding="utf-8")
    function = re.search(r"  async function handleStreamingChat\([^\n]*\) \{[\s\S]*?\n  \}", source).group()
    function += "\n" + re.search(r"  async function performStreamingChat\([^\n]*\) \{[\s\S]*?\n  \}", source).group()
    function += "\n" + "\n".join(re.search(r"  function " + name + r"\([^\n]*\) \{[\s\S]*?\n  \}", source).group()
                                  for name in ["profileLevelText", "currentProfileTag", "activeProfileTag", "recordTruthTurnAlert"])
    probe = r'''
const assert = require('node:assert/strict');
class Element {
  constructor(){this.children=[]; this.style={}; this.value='';}
  append(...items){this.children.push(...items);}
  remove(){}
  replaceChildren(...items){this.children=items;}
  addEventListener(){}
  set textContent(value){this.children=[String(value)];}
  get textContent(){return this.children.map(x=>typeof x==='string'?x:x.textContent).join(' ');}
}
let truthTurnCounter=0, activeChatController=null;
const clearChatEmptyState=()=>{};
const nodes=new Map();
const byId=id=>{if(!nodes.has(id))nodes.set(id,new Element());return nodes.get(id);};
const document={createElement:()=>new Element()};
const state={ownerId:'owner',selectedPersona:'custom-user'};
const PERSONAS={}, DEFAULT_USER_PROFILE={}, llmConfig={}, chatHistory=[];
const refreshSessionTruth=async()=>({revision:1,status:'LOCKED'});
const setError=message=>{throw Error(message);};
const saveCopilotChatHistory=()=>{};
const buildPipelineStepItem=()=>new Element();
let completed=0;
const setPipelineStepState=(item,state)=>{if(state==='completed')completed++;};
let wire='';
const fetch=async()=>new Response(new ReadableStream({start(controller){
  controller.enqueue(new TextEncoder().encode(wire));controller.close();
}}));
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

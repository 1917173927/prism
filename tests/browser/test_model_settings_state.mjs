import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";

// Exercise the actual form functions without a browser or any real credential.
const source = fs.readFileSync(new URL("../../app/api/static/app.js", import.meta.url), "utf8");
const start = source.indexOf("  const llmConfig = {");
const end = source.indexOf("  // 自定义持仓弹窗交互", start);
const elements = new Map();
const byId = id => {
  if (!elements.has(id)) elements.set(id, {value: "", textContent: "", style: {}, dataset: {}, disabled: false});
  return elements.get(id);
};
const context = vm.createContext({byId, state: {ownerId: "owner", dataMode: "LIVE"}, authenticatedOwner: "owner",
  accountAccessEnabled: true, document: {body: {appendChild() {}}}, setError() {},
  apiError: async () => new Error("request failed"), fetch: null});
vm.runInContext(source.slice(start, end), context);
const run = code => vm.runInContext(code, context);
const settings = {is_configured: true, base_url: "https://api.deepseek.com/v1", model: "saved-model", persistence: "OS_PROTECTED"};

byId("llm-api-key-input").value = "unsaved-draft";
run("updateLLMConfigUI()");
assert.equal(byId("llm-api-key-input").value, "unsaved-draft", "status rendering must not erase input");

let release;
context.fetch = () => new Promise(resolve => { release = resolve; });
const loading = run("loadModelSettings()");
byId("llm-model-input").value = "typed-model";
run("llmFormDirty = true");
release({ok: true, json: async () => settings});
await loading;
assert.equal(byId("llm-api-key-input").value, "unsaved-draft");
assert.equal(byId("llm-model-input").value, "typed-model", "late GET must not overwrite a draft");

let sent;
byId("llm-base-url-input").value = settings.base_url;
context.fetch = async (_url, options) => {
  if (options.method === "PUT") sent = JSON.parse(options.body);
  return {ok: true, json: async () => settings};
};
await run("handleSaveLLMConfig()");
assert.equal(sent.api_key, "unsaved-draft", "save must send what was typed");
assert.equal(sent.model, "typed-model");
assert.equal(byId("llm-api-key-input").value, "", "clear only after successful save");
assert.match(byId("llm-api-key-input").placeholder, /已安全保存/);
assert.match(byId("llm-config-status").textContent, /持久化/);

byId("llm-api-key-input").value = "keep-on-error";
context.fetch = async () => ({ok: false});
await run("handleSaveLLMConfig()");
assert.equal(byId("llm-api-key-input").value, "keep-on-error");
assert.equal(byId("llm-api-key-input").disabled, false);

let deleted = false;
context.fetch = async (_url, options) => {
  if (options.method === "DELETE") deleted = true;
  return {ok: true, json: async () => ({...settings, is_configured: false})};
};
await run("handleClearLLMConfig()");
assert.equal(deleted, true);
console.log("PASS: draft survives status/load, save sends draft, explicit delete");

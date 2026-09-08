from pathlib import Path
import re
import shutil
import subprocess

import pytest


def test_mode_change_refreshes_truth_after_restoring_mode_portfolio():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js required")
    source = Path("app/api/static/app.js").read_text(encoding="utf-8")
    function = re.search(r"  async function handleConfirmDataModeSwitch\([^\n]*\) \{[\s\S]*?\n  \}", source).group()
    probe = r'''
const assert = require('node:assert/strict');
const button = {};
const byId = () => button;
const state = {dataMode:'MOCK',modeRevision:1,liveConfigured:true};
const microStore = {transact:fn=>fn(state)};
const invalidateDerivedState=()=>{}, renderInvalidatedDerivedState=()=>{};
const updateRuntimeDataModeUI=()=>{}, closeDataModeConfirmModal=()=>{}, syncNavigation=()=>{};
const alert=message=>{throw Error(message);}, setError=alert;
const fetch=async()=>({status:200,json:async()=>({status:'SUCCESS',data:{data_mode:'LIVE',revision:2,live_ready:true}})});
const events=[];
const loadSavedPortfolio=async()=>{state.portfolio={id:'live-account'};events.push('portfolio');};
const refreshSessionTruth=async()=>{assert.equal(state.dataMode,'LIVE');assert.equal(state.portfolio.id,'live-account');events.push('truth');};
''' + function + r'''
(async()=>{
await handleConfirmDataModeSwitch();
assert.deepEqual(events,['portfolio','truth']);
assert.equal(button.disabled,false);
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
    result = subprocess.run([node, "-e", probe], capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr

from pathlib import Path
import re
import shutil
import subprocess

import pytest


def test_identity_uses_effective_profile_and_clears_unconfirmed_label():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js required")
    source = Path("app/api/static/app.js").read_text(encoding="utf-8")
    functions = "\n".join(re.search(r"  function " + name + r"\([^\n]*\) \{[\s\S]*?\n  \}", source).group()
                          for name in ["profileLevelText", "currentProfileTag", "renderCurrentProfileIdentity"])
    script = '''
const assert=require('node:assert/strict');
const RISK_LEVEL_LABELS={GROWTH:'成长型',CONSERVATIVE:'保守型'};
const PERSONAS={custom:{name:'我的账户',tag:'R3 平衡型'}};
const state={selectedPersona:'custom'};
const nodes={};const byId=id=>(nodes[id]??={});
''' + functions + '''
renderCurrentProfileIdentity({risk_level:'GROWTH',risk_score:73});
assert.equal(byId('custom-profile-chip-name').textContent,'我的账户 (已确认 · 成长型 · 73 分)');
assert.equal(byId('copilot-hero-tag').textContent,'已确认 · 成长型 · 73 分');
renderCurrentProfileIdentity({risk_level:'CONSERVATIVE',risk_score:20});
assert.match(byId('btn-custom-profile-chip').title,/保守型/);
renderCurrentProfileIdentity(null);
assert.equal(byId('copilot-hero-tag').textContent,'待确认问卷');
assert.doesNotMatch(byId('custom-profile-chip-name').textContent,/R3/);
'''
    result = subprocess.run([node, "-e", script], capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr

from pathlib import Path
import shutil
import subprocess

import pytest


def test_stages_respect_dependencies_and_reject_unresolved_graphs():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js required")
    source = Path("app/api/static/workflow-stages.src.js").read_text(encoding="utf-8").replace("export function", "function")
    script = source + '''
const assert=require('node:assert/strict');
const node=(id,deps=[])=>({node_id:id,dependencies:deps,x:0,y:0});
const nodes=[node('c',['a','b']),node('a'),node('b')];
assert.deepEqual(workflowStages(nodes).stages.map(s=>s.map(n=>n.node_id)),[['a','b'],['c']]);
assert.equal(workflowStages([node('a',['b']),node('b',['a'])]).unresolved.length,2);
assert.equal(workflowStages([node('a',['unknown'])]).unresolved.length,1);
assert.deepEqual(workflowStages([]),{stages:[],unresolved:[]});
assert.equal(workflowDraftKey(nodes),workflowDraftKey([node('b'),node('a'),node('c',['b','a'])]));
assert.notEqual(workflowDraftKey(nodes),workflowDraftKey([node('c'),node('a'),node('b')]));
'''
    result = subprocess.run([node, "-e", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

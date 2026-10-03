from pathlib import Path
import re
import shutil
import subprocess

import pytest


@pytest.mark.parametrize("dialog", [
    "portfolio-modal", "portfolio-analysis-drawer", "portfolio-diagnosis-drawer",
])
@pytest.mark.parametrize("previous,requested,closed", [
    ("holdings-report", "profile-questionnaire", True),
    ("holdings-report", "holdings-management", True),
    ("holdings-management", "holdings-report", True),
    ("holdings-report", "holdings-report", False),
])
def test_portfolio_dialog_lifecycle_on_navigation(dialog, previous, requested, closed):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js required for frontend behavior regression")
    source = (Path(__file__).resolve().parents[2] / "app/api/static/app.js").read_text(encoding="utf-8")
    functions = []
    for name in ("syncNavigation", "syncPortfolioDialogScroll"):
        match = re.search(r"  function " + name + r"\([^\n]*\) \{[\s\S]*?\n  \}", source)
        assert match, name
        functions.append(match.group())
    # Native dialog close events are asynchronous.  The DOM adapter deliberately
    # leaves the body scroll class untouched until the navigation code repairs it.
    probe = r'''
const assert = require("node:assert/strict");
const [dialogId, previous, requested, closedText] = process.argv.slice(1);
class Element {
  constructor() {
    this.open = false; this.hidden = false; this.dataset = {}; this.children = [];
    this.classes = new Set(); this.attributes = new Map();
    this.classList = {
      add: value => this.classes.add(value), remove: value => this.classes.delete(value),
      contains: value => this.classes.has(value),
      toggle: (value, enabled) => enabled ? this.classes.add(value) : this.classes.delete(value),
    };
  }
  close() { this.open = false; }
  closest() { return null; }
  setAttribute(key, value) { this.attributes.set(key, value); }
  querySelectorAll() { return []; }
  querySelector() { return null; }
  prepend() {}
  focus() {}
}
const nodes = new Map();
const byId = id => {
  if (!nodes.has(id)) nodes.set(id, new Element());
  return nodes.get(id);
};
const document = {body: new Element(), querySelectorAll: () => []};
const window = {location: {hash: `#${requested}`}, scrollY: 173, scrollTo() {}};
const state = {questionnaireGate: "COMPLETE", ownerId: null};
const DOMAIN_MAP = {profile: "profile", overview: "portfolio"};
const RESEARCH_SUBPAGES = {
  "profile-questionnaire": "profile", "profile-results": "profile", "profile-preferences": "profile",
  "holdings-report": "overview", "holdings-management": "overview",
};
const navigationScrollPositions = new Map();
let activeNavigationRoute = previous;
let navigationScrollFrame = null;
const requestAnimationFrame = callback => { callback(); return 1; };
const cancelAnimationFrame = () => {};
const syncHomeNavigation = () => {};
const syncPortfolioHoldingsLocation = () => {};
const setAgentFeatureToolsOpen = () => {};
const setHomeUploadMenuOpen = () => {};
const setExpertMode = () => {};
const renderOverviewWorkspace = () => {};
''' + "\n".join(functions) + r'''
byId(dialogId).open = true;
document.body.classList.add("portfolio-dialog-open");
syncNavigation(requested);
const closed = closedText === "True";
assert.equal(byId(dialogId).open, !closed, `${dialogId}: ${previous} -> ${requested}`);
assert.equal(document.body.classList.contains("portfolio-dialog-open"), !closed,
  "navigation must synchronously restore scrolling without waiting for close events");
if (previous !== requested) assert.equal(navigationScrollPositions.get(previous), 173);
'''
    result = subprocess.run([node, "-e", probe, dialog, previous, requested, str(closed)],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr

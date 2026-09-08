from pathlib import Path


ROOT = Path(__file__).parents[2]
INDEX = (ROOT / "app/api/static/index.html").read_text(encoding="utf-8")
APP = (ROOT / "app/api/static/app.js").read_text(encoding="utf-8")


def test_regular_workbench_has_five_primary_pages_and_profile_questionnaire() -> None:
    for href in ("#copilot", "#overview", "#stock-research", "#recommendation-history", "#profile"):
        assert href in INDEX
    assert 'id="questionnaire-form"' in INDEX
    assert 'id="questionnaire-summary-content"' not in INDEX
    assert 'id="profile-risk-select"' not in INDEX
    assert 'AI 信任度与解释偏好' in INDEX


def test_system_governance_is_developer_only_and_evaluation_starts_unrun() -> None:
    assert 'class="nav-section-expert collapsed dev-only"' in INDEX
    assert 'id="evaluation-pass-chip">尚未运行' in INDEX
    assert '100.00% 通过' not in INDEX


def test_navigation_keeps_old_hashes_and_profile_is_owner_scoped() -> None:
    assert 'href="#portfolio"' in INDEX
    assert 'portfolio-optimization' in INDEX
    assert 'questionnaire-template' in APP
    assert 'profile/summary' in APP
    assert 'X-Owner-ID' in APP

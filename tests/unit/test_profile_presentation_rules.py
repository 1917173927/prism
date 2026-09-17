from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.profile.behavior import SuitabilityLevel
from app.profile.presentation import (
    _ALLOCATION_RULES,
    _EQUITY_RANGES,
    _feats,
    _persona,
    _service_strategy,
    _tags,
    build_profile_presentation,
)
from app.profile.questionnaire import (
    QUESTIONNAIRE_TEMPLATE,
    QuestionnaireAnswer,
    QuestionnaireSnapshot,
    build_questionnaire_snapshot,
)


NOW = datetime(2026, 9, 17, tzinfo=UTC)


def answers() -> tuple[QuestionnaireAnswer, ...]:
    result = []
    for question in QUESTIONNAIRE_TEMPLATE.questions:
        if question.question_id == "Q13":
            result.append(QuestionnaireAnswer(question_id="Q13", selected_option_ids=()))
        elif question.question_type.value == "SCORE":
            result.append(QuestionnaireAnswer(question_id=question.question_id, score=3))
        else:
            result.append(QuestionnaireAnswer(question_id=question.question_id, selected_option_ids=(question.options[0].option_id,)))
    return tuple(result)


def snapshot() -> QuestionnaireSnapshot:
    return build_questionnaire_snapshot("presentation-rules-owner", answers(), confirmed_at=NOW, snapshot_version=1)


def replace_answer(source: QuestionnaireSnapshot, question_id: str, *option_ids: str) -> QuestionnaireSnapshot:
    updated = tuple(
        QuestionnaireAnswer(question_id=question_id, selected_option_ids=option_ids) if item.question_id == question_id else item
        for item in source.answers
    )
    return source.model_copy(update={"answers": updated})


def scores(**updates: str) -> dict[str, Decimal]:
    base = {key: Decimal("20") for key in ("risk", "exp", "act", "res", "inf", "ai", "per", "aid")}
    base.update({key: Decimal(value) for key, value in updates.items()})
    return base


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (scores(res="80", exp="80", act="70", risk="30"), "自主研究型"),
        (scores(res="80", exp="30", act="20", aid="20"), "深度价值型"),
        (scores(act="80", risk="80", exp="60"), "主动交易型"),
        (scores(ai="80", per="80", exp="60", act="60"), "AI 协作成长型"),
        (scores(risk="55", per="80", act="50", exp="60"), "均衡配置型"),
        (scores(exp="20", aid="80", act="50"), "起步护航型"),
        (scores(risk="30", exp="50", act="50", res="50", ai="50", per="50", aid="50"), "稳健成长型"),
    ],
)
def test_each_persona_has_a_deterministic_positive_case(values, expected) -> None:
    persona, fit, trace = _persona(snapshot(), values)
    assert persona == expected
    assert fit == trace.final_fit


def test_persona_tie_uses_declared_order_and_conflict_penalty_is_visible() -> None:
    persona, fit, trace = _persona(snapshot(), scores(res="60", exp="60", act="40"))
    assert persona == "自主研究型"
    assert fit == Decimal("60.00")
    assert trace.rule_id == "P01"

    conflicted = replace_answer(snapshot(), "Q7", "follow")
    persona, fit, trace = _persona(conflicted, scores(res="80", exp="80", act="80", risk="20"))
    assert persona == "自主研究型"
    assert trace.raw_fit == Decimal("80.00")
    assert trace.conflict_penalty == Decimal("5")
    assert fit == Decimal("75.00")


def test_allocation_rules_are_closed_and_match_the_v2_table() -> None:
    expected = {
        SuitabilityLevel.C1: (("60", "40", "0"), ("0", "0")),
        SuitabilityLevel.C2: (("30", "50", "20"), ("0", "20")),
        SuitabilityLevel.C3: (("10", "50", "40"), ("30", "50")),
        SuitabilityLevel.C4: (("10", "20", "70"), ("60", "80")),
        SuitabilityLevel.C5: (("5", "0", "95"), ("80", "100")),
    }
    for level, (targets, equity_range) in expected.items():
        actual = tuple(str(item[2]) for item in _ALLOCATION_RULES[level])
        assert actual == targets
        assert sum((item[2] for item in _ALLOCATION_RULES[level]), Decimal("0")) == 100
        assert tuple(str(item) for item in _EQUITY_RANGES[level]) == equity_range


def test_tags_are_ordered_unique_and_bounded() -> None:
    values, trace = _tags(scores(risk="65", exp="70", act="66", res="58", ai="60", per="52"))
    assert values == ("高风险偏好", "经验丰富", "主动操作", "深度研究", "AI 协作", "重视个性化")
    assert len(values) == len(set(values)) == len(trace) == 6

    values, _ = _tags(scores(risk="44.99", exp="41.99", act="34.99", res="57.99", inf="59.99", ai="39.99"))
    assert values == ("稳健风险偏好", "投资入门", "低频长线", "简洁决策", "谨慎使用 AI")


def test_ten_service_rules_have_hit_and_miss_coverage() -> None:
    scene_snapshot = replace_answer(snapshot(), "Q13", "portfolio")
    _, high_trace = _service_strategy(scene_snapshot, scores(exp="80", aid="80", res="80", inf="80", act="80", per="80", ai="80"))
    _, low_trace = _service_strategy(snapshot(), scores(exp="20", aid="20", res="20", inf="20", act="20", per="20", ai="20"))
    assert {item.rule_id for item in (*high_trace, *low_trace)} == {f"S{index:02d}" for index in range(1, 11)}
    assert all(item.rule_id not in {entry.rule_id for entry in low_trace} for item in high_trace if item.rule_id in {"S02", "S03", "S04", "S05", "S07", "S08", "S10"})


def test_q13_mapping_preserves_order_deduplicates_and_defaults() -> None:
    feats, trace = _feats(snapshot())
    assert feats == ("market", "stock", "optimize")
    assert trace.defaulted is True

    selected = replace_answer(snapshot(), "Q13", "risk", "portfolio", "bond", "stock", "market")
    feats, trace = _feats(selected)
    assert feats == ("optimize", "bond", "stock")
    assert trace.defaulted is False
    assert trace.selected_option_ids == ("risk", "portfolio", "bond", "stock", "market")


@pytest.mark.parametrize(
    ("option_id", "expected"),
    [
        ("market", "market"),
        ("industry", "industry"),
        ("stock", "stock"),
        ("fund", "fund"),
        ("bond", "bond"),
        ("portfolio", "optimize"),
        ("risk", "optimize"),
    ],
)
def test_each_q13_option_maps_to_a_public_feature(option_id: str, expected: str) -> None:
    feats, trace = _feats(replace_answer(snapshot(), "Q13", option_id))
    assert feats == (expected,)
    assert trace.mappings == (f"{option_id}→{expected}",)


def test_legacy_snapshot_replays_v1_presentation_without_rewrite() -> None:
    current = snapshot()
    legacy_payload = current.model_dump(mode="python")
    legacy_payload["questionnaire_version"] = "investor-questionnaire.v1"
    legacy_payload["ruleset_version"] = "investor-questionnaire-rules.v1"
    legacy = QuestionnaireSnapshot.model_validate(legacy_payload)
    presentation = build_profile_presentation(legacy)
    assert presentation.schema_version == "profile-presentation.v1"
    assert presentation.persona is None
    assert presentation.rule_trace is None
    assert presentation.ruleset_version == "investor-profile-presentation-rules.v1"

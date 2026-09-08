from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.profile.questionnaire import (
    DIMENSION_KEYS,
    QUESTIONNAIRE_TEMPLATE,
    QuestionnaireAnswer,
    build_questionnaire_snapshot,
    score_answers,
    validate_answers,
)


def answers() -> tuple[QuestionnaireAnswer, ...]:
    result = []
    for question in QUESTIONNAIRE_TEMPLATE.questions:
        if question.question_type.value == "SCORE":
            result.append(QuestionnaireAnswer(question_id=question.question_id, score=3))
        else:
            result.append(QuestionnaireAnswer(
                question_id=question.question_id,
                selected_option_ids=(question.options[0].option_id,),
            ))
    return tuple(result)


def test_template_has_six_sections_and_all_nineteen_questions() -> None:
    assert len(QUESTIONNAIRE_TEMPLATE.sections) == 6
    assert [item.question_id for item in QUESTIONNAIRE_TEMPLATE.questions] == [f"Q{i}" for i in range(1, 20)]
    assert tuple(item.key for item in score_answers(answers())) == DIMENSION_KEYS


def test_questionnaire_validation_rejects_missing_duplicate_and_unknown_answers() -> None:
    valid = answers()
    with pytest.raises(ValueError, match="19"):
        validate_answers(valid[:-1])
    with pytest.raises(ValueError, match="duplicate"):
        validate_answers(valid[:-1] + (valid[0],))
    unknown = valid[:-1] + (QuestionnaireAnswer(question_id="Q20", selected_option_ids=("x",)),)
    with pytest.raises(ValueError, match="Q1 through Q19"):
        validate_answers(unknown)


def test_snapshot_is_deterministic_and_preserves_eight_dimensions() -> None:
    now = datetime(2026, 9, 8, tzinfo=UTC)
    first = build_questionnaire_snapshot("questionnaire-owner", answers(), confirmed_at=now, snapshot_version=1)
    second = build_questionnaire_snapshot("questionnaire-owner", answers(), confirmed_at=now, snapshot_version=1)
    assert first.snapshot_id == second.snapshot_id
    assert first.dimensions[0].key == "risk"
    assert first.profile.owner_id == "questionnaire-owner"
    assert Decimal("0") <= first.risk_score <= Decimal("100")

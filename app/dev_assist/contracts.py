"""Contracts for the non-executing development-assistance workflow."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Self

from pydantic import Field, model_validator

from app.contracts.evidence import ContractModel, NonEmptyStr


class DevAssistRequest(ContractModel):
    schema_version: Literal["dev-assist-request.v1"] = "dev-assist-request.v1"
    run_id: NonEmptyStr
    owner_id: NonEmptyStr
    requested_at: datetime
    prd_text: NonEmptyStr
    technical_text: NonEmptyStr
    target_stack: NonEmptyStr = "Python 3.11, FastAPI, Pydantic, vanilla JavaScript"

    @model_validator(mode="after")
    def validate_request(self) -> Self:
        if self.requested_at.tzinfo is None or self.requested_at.utcoffset() is None:
            raise ValueError("requested_at must be timezone-aware")
        if len(self.prd_text) > 200_000 or len(self.technical_text) > 200_000:
            raise ValueError("development documents exceed the bounded text limit")
        return self


class DevAssistApiDraft(ContractModel):
    method: Literal["GET", "POST", "PATCH"]
    path: NonEmptyStr
    purpose: NonEmptyStr


class DevAssistSkeletonFile(ContractModel):
    path: NonEmptyStr
    language: Literal["python", "javascript"]
    content: NonEmptyStr


class DevAssistResponse(ContractModel):
    schema_version: Literal["dev-assist-response.v1"] = "dev-assist-response.v1"
    run_id: NonEmptyStr
    owner_id: NonEmptyStr
    generated_at: datetime
    status: Literal["CALCULATED", "REVIEW_REQUIRED"]
    conflicts: tuple[NonEmptyStr, ...]
    gaps: tuple[NonEmptyStr, ...]
    improved_technical_spec: NonEmptyStr
    api_drafts: tuple[DevAssistApiDraft, ...]
    data_models: tuple[NonEmptyStr, ...]
    state_flow: tuple[NonEmptyStr, ...]
    test_cases: tuple[NonEmptyStr, ...]
    acceptance_criteria: tuple[NonEmptyStr, ...]
    skeleton_files: tuple[DevAssistSkeletonFile, ...] = Field(min_length=3)
    assumptions: tuple[NonEmptyStr, ...]
    requires_human_decision: tuple[NonEmptyStr, ...]
    execution_performed: Literal[False] = False

    @model_validator(mode="after")
    def validate_response(self) -> Self:
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
        if len({item.path for item in self.skeleton_files}) != len(self.skeleton_files):
            raise ValueError("skeleton file paths must be unique")
        return self

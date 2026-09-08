"""Owner-scoped confirmation record for an OCR-derived portfolio."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Self

from pydantic import model_validator

from app.contracts.evidence import ContractModel, NonEmptyStr
from app.portfolio.contracts import PortfolioImportBundle


class PortfolioOcrConfirmation(ContractModel):
    schema_version: Literal["portfolio-ocr-confirmation.v1"] = "portfolio-ocr-confirmation.v1"
    confirmation_id: NonEmptyStr
    owner_id: NonEmptyStr
    image_digest: NonEmptyStr
    confirmed_payload_hash: NonEmptyStr
    confirmed_at: datetime
    portfolio: PortfolioImportBundle

    @model_validator(mode="after")
    def validate_confirmation(self) -> Self:
        if self.confirmed_at.tzinfo is None or self.confirmed_at.utcoffset() is None:
            raise ValueError("confirmed_at must be timezone-aware")
        if len(self.image_digest) != 64 or any(char not in "0123456789abcdef" for char in self.image_digest):
            raise ValueError("image_digest must be a lowercase SHA-256 digest")
        if len(self.confirmed_payload_hash) != 64 or any(
            char not in "0123456789abcdef" for char in self.confirmed_payload_hash
        ):
            raise ValueError("confirmed_payload_hash must be a lowercase SHA-256 digest")
        if self.portfolio.owner_id != self.owner_id:
            raise ValueError("portfolio owner does not match confirmation owner")
        return self


__all__ = ["PortfolioOcrConfirmation"]

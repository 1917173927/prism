"""Exchange-code validation shared by direct and conversational tools."""

from __future__ import annotations

import re


CONVERTIBLE_BOND_CODE_PREFIXES = ("110", "111", "113", "118", "123", "127", "128")


def invalid_explicit_convertible_bond_code(subject: str) -> str | None:
    """Return an invalid explicit code while leaving semantic screens untouched."""
    normalized = subject.strip()
    match = re.match(
        r"(\d{6})(?:\.(?:SH|SZ))?(?:\s|$)",
        normalized,
        flags=re.IGNORECASE,
    )
    if match is None:
        match = re.search(
            r"(?:可转债投资|可转债|转债)\s*[：:]?\s*(\d{6})(?:\.(?:SH|SZ))?",
            normalized,
            flags=re.IGNORECASE,
        )
    if match is None:
        match = re.fullmatch(
            r"(\d{6})(?:\.(?:SH|SZ))?", normalized, flags=re.IGNORECASE
        )
    if match is None:
        return None
    code = match.group(1)
    return None if code.startswith(CONVERTIBLE_BOND_CODE_PREFIXES) else code

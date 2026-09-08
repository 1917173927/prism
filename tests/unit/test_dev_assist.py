from datetime import UTC, datetime
from io import BytesIO
from zipfile import ZipFile

import pytest

from app.dev_assist import DevAssistError, DevAssistRequest, extract_document_text, run_dev_assist


NOW = datetime(2026, 9, 8, 9, 0, tzinfo=UTC)


def test_dev_assist_returns_non_executing_structured_skeleton() -> None:
    request = DevAssistRequest(
        run_id="dev-run-001",
        owner_id="dev-owner-001",
        requested_at=NOW,
        prd_text="需要实时组合分析、接口和验收标准。",
        technical_text="采用 fixture 数据，不交易，包含 owner 权限和测试。",
    )
    result = run_dev_assist(request, generated_at=NOW)
    assert result.status == "REVIEW_REQUIRED"
    assert result.conflicts
    assert result.execution_performed is False
    assert {item.path for item in result.skeleton_files} == {
        "app/contracts.py", "app/routes.py", "tests/test_feature.py"
    }
    compile(next(item.content for item in result.skeleton_files if item.path == "app/contracts.py"), "contracts.py", "exec")
    compile(next(item.content for item in result.skeleton_files if item.path == "app/routes.py"), "routes.py", "exec")


def test_document_extraction_supports_utf8_and_docx() -> None:
    assert extract_document_text("prd.md", "产品需求".encode()) == "产品需求"
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>技术方案</w:t></w:r></w:p></w:body></w:document>',
        )
    assert extract_document_text("technical.docx", buffer.getvalue()) == "技术方案"
    with pytest.raises(DevAssistError, match="supported"):
        extract_document_text("prd.pdf", b"not a pdf")


def test_document_extraction_rejects_invalid_document_xml() -> None:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", b"<invalid>")
    with pytest.raises(DevAssistError, match="XML"):
        extract_document_text("broken.docx", buffer.getvalue())

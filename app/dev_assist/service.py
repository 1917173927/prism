"""Bounded local document extraction and deterministic implementation scaffolding."""

from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
from pathlib import PurePosixPath
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from app.dev_assist.contracts import (
    DevAssistApiDraft,
    DevAssistRequest,
    DevAssistResponse,
    DevAssistSkeletonFile,
)


class DevAssistError(ValueError):
    """A safe refusal for invalid development-assistance inputs."""


ALLOWED_DOCUMENT_EXTENSIONS = {".docx", ".md", ".txt"}
MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
MAX_DOCX_UNCOMPRESSED_BYTES = 8 * 1024 * 1024


def extract_document_text(filename: str, content: bytes) -> str:
    suffix = PurePosixPath(filename.strip()).suffix.casefold()
    if suffix not in ALLOWED_DOCUMENT_EXTENSIONS:
        raise DevAssistError("only .docx, .md and .txt documents are supported")
    if not content or len(content) > MAX_DOCUMENT_BYTES:
        raise DevAssistError("document size must be between 1 byte and 2 MiB")
    if suffix in {".md", ".txt"}:
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DevAssistError("text document must use UTF-8") from exc
    else:
        try:
            with ZipFile(BytesIO(content)) as archive:
                if sum(item.file_size for item in archive.infolist()) > MAX_DOCX_UNCOMPRESSED_BYTES:
                    raise DevAssistError("DOCX expanded content exceeds the safe limit")
                xml = archive.read("word/document.xml")
        except (BadZipFile, KeyError, OSError, RuntimeError) as exc:
            raise DevAssistError("DOCX package is invalid") from exc
        try:
            root = ElementTree.fromstring(xml)
        except ElementTree.ParseError as exc:
            raise DevAssistError("DOCX document XML is invalid") from exc
        namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        paragraphs: list[str] = []
        for paragraph in root.iter(namespace + "p"):
            value = "".join(node.text or "" for node in paragraph.iter(namespace + "t")).strip()
            if value:
                paragraphs.append(value)
        text = "\n".join(paragraphs)
    normalized = text.strip()
    if not normalized:
        raise DevAssistError("document contains no readable text")
    if len(normalized) > 200_000:
        raise DevAssistError("extracted document text exceeds the bounded limit")
    return normalized


def _has(text: str, *terms: str) -> bool:
    folded = text.casefold()
    return any(term.casefold() in folded for term in terms)


def run_dev_assist(request: DevAssistRequest, *, generated_at: datetime | None = None) -> DevAssistResponse:
    combined = request.prd_text + "\n" + request.technical_text
    gaps: list[str] = []
    checks = (
        (("验收", "acceptance"), "缺少可验证的验收标准和失败判定。"),
        (("接口", "api"), "缺少公开接口、请求响应及错误契约。"),
        (("权限", "鉴权", "owner"), "缺少身份、权限或租户隔离边界。"),
        (("异常", "失败", "降级"), "缺少异常、超时和降级路径。"),
        (("测试", "test"), "缺少单元、集成和端到端测试策略。"),
    )
    for terms, message in checks:
        if not _has(combined, *terms):
            gaps.append(message)
    conflicts: list[str] = []
    if _has(request.prd_text, "自动执行", "自动下单") and _has(request.technical_text, "不交易", "禁止交易"):
        conflicts.append("PRD 的自动执行要求与技术方案的禁止交易边界冲突。")
    if _has(request.prd_text, "实时") and _has(request.technical_text, "fixture", "模拟数据"):
        conflicts.append("PRD 的实时数据表述与技术方案的离线数据模式冲突。")

    improved = (
        "目标：在明确 owner 隔离、输入契约和失败状态的前提下交付可审计纵切。\n"
        "输入：只接受经过类型校验的 PRD、技术方案和业务数据；原始文本不作为金融事实。\n"
        "处理：模型仅负责结构化提取和表述，所有金额、比例、风险与状态由确定性代码计算。\n"
        "输出：返回版本化响应、结构化问题清单、证据来源和可复现测试结果。\n"
        "安全：禁止自动交易、凭据回显、跨 owner 访问和未经确认的数据升级。\n"
        f"目标技术栈：{request.target_stack}。"
    )
    api_drafts = (
        DevAssistApiDraft(method="POST", path="/api/v1/features/runs", purpose="提交强类型业务输入并启动计算"),
        DevAssistApiDraft(method="GET", path="/api/v1/features/runs/{run_id}", purpose="读取 owner 隔离的运行结果"),
    )
    skeleton_files = (
        DevAssistSkeletonFile(
            path="app/contracts.py",
            language="python",
            content=(
                "from pydantic import BaseModel, ConfigDict\n\n"
                "class FeatureRequest(BaseModel):\n"
                "    model_config = ConfigDict(extra='forbid', frozen=True)\n"
                "    owner_id: str\n"
                "    request_id: str\n"
            ),
        ),
        DevAssistSkeletonFile(
            path="app/routes.py",
            language="python",
            content=(
                "from fastapi import APIRouter\n"
                "from .contracts import FeatureRequest\n\n"
                "router = APIRouter(prefix='/api/v1/features')\n\n"
                "@router.post('/runs')\n"
                "def create_run(request: FeatureRequest) -> dict[str, str]:\n"
                "    return {'request_id': request.request_id, 'status': 'CALCULATED'}\n"
            ),
        ),
        DevAssistSkeletonFile(
            path="tests/test_feature.py",
            language="python",
            content=(
                "from app.contracts import FeatureRequest\n\n"
                "def test_request_contract() -> None:\n"
                "    request = FeatureRequest(owner_id='owner-1', request_id='run-1')\n"
                "    assert request.owner_id == 'owner-1'\n"
            ),
        ),
    )
    decisions = tuple(
        item for item in (
            "确认生产身份认证方案。" if not _has(combined, "oauth", "jwt", "身份认证") else None,
            "确认真实数据提供商和授权方式。" if _has(request.prd_text, "实时") and not _has(request.technical_text, "provider", "数据源") else None,
        ) if item is not None
    )
    return DevAssistResponse(
        run_id=request.run_id,
        owner_id=request.owner_id,
        generated_at=generated_at or datetime.now(UTC),
        status="REVIEW_REQUIRED" if conflicts or decisions else "CALCULATED",
        conflicts=tuple(conflicts),
        gaps=tuple(gaps),
        improved_technical_spec=improved,
        api_drafts=api_drafts,
        data_models=("FeatureRequest", "FeatureRun", "FeatureEvidence", "FeatureIssue"),
        state_flow=("RECEIVED", "VALIDATED", "CALCULATED", "REVIEW_REQUIRED", "COMPLETED"),
        test_cases=(
            "有效输入产生稳定响应。",
            "额外字段和跨 owner 请求被拒绝。",
            "缺失证据保持 REVIEW_REQUIRED。",
            "生成骨架仅返回文本且不执行。",
        ),
        acceptance_criteria=(
            "相同输入与时间锚点生成相同结构。",
            "所有风险和金额计算均由确定性代码完成。",
            "输出不含凭据、原始异常或交易副作用。",
        ),
        skeleton_files=skeleton_files,
        assumptions=("代码骨架以当前 Prism 技术栈为默认目标。", "文档内容仅作为参考输入，不作为运行指令。"),
        requires_human_decision=decisions,
    )

"""将 24 张纯中文低密度清晰流程图精确替换进 S2 解决方案 Word 文档。"""

from __future__ import annotations

import io
import re
import shutil
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC_DOCX = ROOT / "docs/submission/s2-figure-revision/S2-解决方案-图片修改版.docx"
OUT_DOCX = ROOT / "docs/submission/S2-解决方案-清晰流程图版.docx"
FIG_DIR = ROOT / "docs/submission/figures-clean-cn"

# 目标图片映射：Word 内原媒体路径 -> 新生成的高清纯中文图
MEDIA_MAP = {
    "word/media/01-investor-needs.png": "图1-01-投资者信息需求与服务设计.png",
    "word/media/02-service-cycle.png": "图1-02-个性化投顾服务流程.png",
    "word/media/03-technical-route.png": "图1-03-系统技术路线.png",
    "word/media/04-delivery-materials.png": "图2-01-项目成果交付组织.png",
    "word/media/05-business-process.png": "图2-02-核心业务流程.png",
    "word/media/image4.png": "图3-01-系统技术架构.png",
    "word/media/image5.png": "图3-02-提示词组织与工具处理.png",
    "word/media/image6.png": "图3-03-前端交互与状态框架.png",
    "word/media/image7.png": "图3-04-后端分层服务框架.png",
    "word/media/image8.png": "图3-05-工作台页面入口与反馈.png",
    "word/media/image9.png": "图3-06-数据库外键关系.png",
    "word/media/image10.png": "图3-07-资料版本与应用层关联.png",
    "word/media/image11.png": "图3-08-金融数据状态与处理.png",
    "word/media/image12.png": "图3-09-画像与预算映射流程.png",
    "word/media/image13.png": "图3-10-持仓穿透与集中度计算.png",
    "word/media/image14.png": "图3-11-再平衡数量与现金计算.png",
    "word/media/image15.png": "图3-12-研究调度与时间预算.png",
    "word/media/image16.png": "图3-13-来源分组与证据验证.png",
    "word/media/image17.png": "图3-14-风险与合规审查.png",
    "word/media/image18.png": "图3-15-研究资料提取与检索.png",
    "word/media/image19.png": "图3-16-会话上下文与工具处理.png",
    "word/media/image20.png": "图3-17-会话前提状态流转.png",
    "word/media/image21.png": "图3-18-确定性研究算法流程.png",
    "word/media/24-costs.png": "图4-01-成本结构占比.png",
}

# 144 mm 宽度（适配 A4 正文可排宽度 146.5 mm，图中 10.5pt 主字号实际呈现约 10.3pt，略小于 12pt 正文）
TARGET_WIDTH_MM = 144.0
MAX_HEIGHT_MM = 185.0
EMU_PER_MM = 36000


def compute_emu_size(png_path: Path) -> tuple[int, int]:
    with Image.open(png_path) as im:
        pw, ph = im.size
    w_mm = TARGET_WIDTH_MM
    h_mm = w_mm * ph / pw
    if h_mm > MAX_HEIGHT_MM:
        h_mm = MAX_HEIGHT_MM
        w_mm = h_mm * pw / ph
    return round(w_mm * EMU_PER_MM), round(h_mm * EMU_PER_MM)


def update_document_xml(doc_xml: bytes, rid_to_size: dict[str, tuple[int, int]]) -> bytes:
    """使用正则精准更新对应 rId 所在 <w:drawing> 内的 wp:extent 与 a:ext，完整保留原始 XML 命名空间与前缀。"""
    text = doc_xml.decode("utf-8")
    updated = 0

    def repl_drawing(match: re.Match[str]) -> str:
        nonlocal updated
        block = match.group(0)
        rid_m = re.search(r'r:embed="([^"]+)"', block)
        if not rid_m:
            return block
        rid = rid_m.group(1)
        if rid not in rid_to_size:
            return block
        cx, cy = rid_to_size[rid]
        block = re.sub(
            r'(<wp:extent\b[^>]*\bcx=")\d+("[^>]*\bcy=")\d+(")',
            rf"\g<1>{cx}\g<2>{cy}\g<3>",
            block,
        )
        block = re.sub(
            r'(<a:ext\b[^>]*\bcx=")\d+("[^>]*\bcy=")\d+(")',
            rf"\g<1>{cx}\g<2>{cy}\g<3>",
            block,
        )
        # 移除旧裁剪框（若有）
        block = re.sub(r"<a:srcRect\b[^>]*/>", "", block)
        updated += 1
        return block

    new_text = re.sub(r"<w:drawing\b.*?</w:drawing>", repl_drawing, text, flags=re.DOTALL)
    if updated != len(rid_to_size):
        raise RuntimeError(f"期望更新 {len(rid_to_size)} 处 drawing，实际更新 {updated} 处")
    # 验证修改后的 XML 语法完全合法
    ET.fromstring(new_text.encode("utf-8"))
    return new_text.encode("utf-8")


def main() -> None:
    if not SRC_DOCX.exists():
        raise FileNotFoundError(f"未找到源文档：{SRC_DOCX}")

    # 校验全部 24 张新图存在且有效
    new_bytes: dict[str, bytes] = {}
    new_sizes: dict[str, tuple[int, int]] = {}
    for media_path, fig_name in MEDIA_MAP.items():
        fig_path = FIG_DIR / fig_name
        if not fig_path.exists():
            raise FileNotFoundError(f"缺少新图：{fig_path}")
        new_bytes[media_path] = fig_path.read_bytes()
        new_sizes[media_path] = compute_emu_size(fig_path)

    with zipfile.ZipFile(SRC_DOCX, "r") as zin:
        rels_root = ET.fromstring(zin.read("word/_rels/document.xml.rels"))
        rid_to_size: dict[str, tuple[int, int]] = {}
        for rel in rels_root:
            target = "word/" + rel.attrib["Target"].lstrip("/")
            if target in new_sizes:
                rid_to_size[rel.attrib["Id"]] = new_sizes[target]
        if len(rid_to_size) != len(MEDIA_MAP):
            raise RuntimeError(f"rId 映射数量不匹配：{len(rid_to_size)} vs {len(MEDIA_MAP)}")

        new_doc_xml = update_document_xml(zin.read("word/document.xml"), rid_to_size)

        tmp_out = OUT_DOCX.with_suffix(".tmp.docx")
        with zipfile.ZipFile(tmp_out, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                if item.filename == "word/document.xml":
                    zout.writestr(item, new_doc_xml)
                elif item.filename in new_bytes:
                    zout.writestr(item, new_bytes[item.filename])
                else:
                    zout.writestr(item, zin.read(item.filename))

    tmp_out.replace(OUT_DOCX)
    shutil.copy2(OUT_DOCX, SRC_DOCX)

    # 最终核验
    with zipfile.ZipFile(OUT_DOCX, "r") as zcheck:
        ET.fromstring(zcheck.read("word/document.xml"))
        for media_path, expected in new_bytes.items():
            actual = zcheck.read(media_path)
            assert actual == expected, f"媒体内容不一致：{media_path}"
            with Image.open(io.BytesIO(actual)) as im:
                im.verify()

    print(f"成功替换 {len(MEDIA_MAP)} 张清晰流程图并完成 XML/PNG 校验：")
    print(f"  - {OUT_DOCX}")
    print(f"  - {SRC_DOCX}")


if __name__ == "__main__":
    main()

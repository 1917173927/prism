from argparse import ArgumentParser
from collections import Counter
from hashlib import sha256
from pathlib import Path
import json
import re

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
from lxml import etree
import pdfplumber
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "output/s2c-authoring"
TARGET = ROOT / "docs/submission/Prism-S2C-技术路线及实现方案.docx"


def normalized(text):
    return re.sub(r"\s+", "", text)


def main():
    parser = ArgumentParser()
    parser.add_argument("--template", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads((WORK / "build-report.json").read_text(encoding="utf-8"))
    doc = Document(TARGET)
    reference = Document(args.template)
    actual = []
    for element in doc._element.body:
        if element.tag == qn("w:p"):
            text = Paragraph(element, doc._body).text
            if text:
                actual.append(text)
        elif element.tag == qn("w:tbl"):
            for row in Table(element, doc._body).rows:
                actual.extend(cell.text for cell in row.cells)
    if actual != report["expected_text"]:
        raise ValueError("DOCX text does not match Markdown content")
    chapters = [p.text for p in doc.paragraphs if p.style.name == "Heading 1"]
    expected = ["3.1 项目总体设计", "3.2 界面设计", "3.3 数据库设计", "3.4 系统关键技术实现", "3.5 系统主要界面"]
    if chapters != expected:
        raise ValueError("chapter scope differs from request")
    fulltext = "\n".join(actual)
    forbidden = [term for term in ["创新", "3.6", "不是", "而是", "契约", "栈", "落", "死", "拆", "偏"] if term in fulltext]
    if forbidden:
        raise ValueError(f"unexpected document terms: {forbidden}")
    if len(doc.tables) != 13 or len(doc.inline_shapes) != 12:
        raise ValueError("table or figure count differs from source")
    for key in ["page_width", "page_height", "top_margin", "bottom_margin", "left_margin", "right_margin"]:
        if getattr(doc.sections[0], key) != getattr(reference.sections[-1], key):
            raise ValueError(f"reference geometry mismatch: {key}")
    font_sizes = {"Title": 26, "Heading 1": 18, "Heading 2": 15, "Heading 3": 14}
    for item in doc.paragraphs:
        if item.style.name in font_sizes:
            if any(run.font.size.pt != font_sizes[item.style.name] for run in item.runs if run.text):
                raise ValueError("heading font size mismatch")
        if item.text and any(run.font.name != "楷体" for run in item.runs if run.text):
            raise ValueError("paragraph font family mismatch")
    printable = doc.sections[0].page_width - doc.sections[0].left_margin - doc.sections[0].right_margin
    for table in doc.tables:
        if len(table.columns) not in {4, 5}:
            raise ValueError("unexpected column count")
        if abs(sum(column.width for column in table.columns) - printable) > 635 * len(table.columns):
            raise ValueError("table exceeds printable width")
        if table.rows[0]._tr.get_or_add_trPr().find(qn("w:tblHeader")) is None:
            raise ValueError("table header must repeat")
        if any(row._tr.get_or_add_trPr().find(qn("w:cantSplit")) is None for row in table.rows):
            raise ValueError("table row may split between pages")
    image_references = doc._element.xpath(".//a:blip/@r:embed")
    if len(image_references) != 12 or any(key not in doc.part.rels for key in image_references):
        raise ValueError("figure relationship missing")
    for figure, key in zip(report["figures"], image_references, strict=True):
        relationship = doc.part.rels[key]
        if sha256(relationship.target_part.blob).hexdigest() != figure["sha256"]:
            raise ValueError("figure bytes changed")
    pdf_path = WORK / "Prism-S2C-技术路线及实现方案.pdf"
    pdf = PdfReader(pdf_path)
    pages = []
    pdf_text = []
    with pdfplumber.open(pdf_path) as rendered:
        for index, page in enumerate(rendered.pages, 1):
            text = page.extract_text(x_tolerance=1, y_tolerance=3) or ""
            pdf_text.append(text)
            outside = [character for character in page.chars
                       if character["x0"] < -1 or character["x1"] > page.width + 1
                       or character["top"] < -1 or character["bottom"] > page.height + 1]
            outside_images = [item for item in page.images
                              if item["x0"] < -1 or item["x1"] > page.width + 1
                              or item["top"] < -1 or item["bottom"] > page.height + 1]
            if outside or outside_images:
                raise ValueError(f"content exceeds page boundary: {index}")
            for image in page.images:
                overlapping = [character for character in page.chars
                               if character["x0"] < image["x1"] - 0.5
                               and character["x1"] > image["x0"] + 0.5
                               and character["top"] < image["bottom"] - 0.5
                               and character["bottom"] > image["top"] + 0.5]
                if overlapping:
                    raise ValueError(f"text overlaps figure boundary: {index}")
            if not text.strip() and not page.images:
                raise ValueError(f"unexpected blank page: {index}")
            pages.append({"page": index, "characters": len(page.chars), "images": len(page.images),
                          "first_text": text[:100], "page_boundary": "PASS"})
    joined = normalized("\n".join(pdf_text))
    for heading in report["headings"]:
        if normalized(heading) not in joined:
            raise ValueError(f"heading missing from PDF: {heading}")
    required = Counter(normalized(fulltext))
    available = Counter(joined)
    missing = {key: value - available[key] for key, value in required.items() if value > available[key]}
    if missing:
        raise ValueError(f"text characters missing from PDF: {missing}")
    if sha256(args.template.read_bytes()).hexdigest() != report["template_sha256"]:
        raise ValueError("reference changed")
    # SVG 文字通过 XML 库读取，验证复用图形的来源结构。
    svg_titles = {}
    for name in ["frontend-framework", "backend-framework", "context-dataflow", "judge-03-profile-calculation",
                 "judge-04-evidence-validation", "judge-05-rebalancing", "judge-06-decision-gates"]:
        tree = etree.parse(str(ROOT / "docs/submission/figures" / (name + ".svg")))
        svg_titles[name] = tree.xpath("//*[local-name()='text']//text()")
    result = {"status": "PASS", "document": str(TARGET), "pages": len(pdf.pages),
              "chapters": chapters, "tables": len(doc.tables), "figures": len(doc.inline_shapes),
              "text_matches_source": True, "source_characters": len(normalized(fulltext)),
              "reference_unchanged": True, "template_geometry": "PASS", "heading_fonts": "PASS",
              "pdf_text_coverage": "PASS", "page_boundaries": "PASS", "page_details": pages,
              "svg_text": svg_titles, "visual_review": "NOT_PERFORMED_USER_RESTRICTION",
              "sha256": sha256(TARGET.read_bytes()).hexdigest()}
    (WORK / "verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: result[key] for key in ["status", "pages", "tables", "figures", "source_characters",
                                                  "reference_unchanged", "pdf_text_coverage", "page_boundaries"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

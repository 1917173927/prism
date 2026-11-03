"""Append evidence-grounded innovations while retaining the supplied DOCX styles."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile

from lxml import etree

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

INTRO = (
    "Prism 的创新集中于面向个人组合的可信决策机制：把已确认画像、实际持仓、研究证据和输出审查连接起来，"
    "使个性化条件能够影响计算，使结论能够追溯到依据，并在资料变化后重新核验。"
    "以下五项创新均对应现有模块及自动化测试，体现为系统机制与工程集成创新。"
)
ROWS = [
    ["创新方向", "改进的问题", "核心机制", "验证依据"],
    ["画像参与计算", "风险等级难以约束实际仓位", "画像版本映射预算，逐项比较组合暴露", "固定同仓场景产生保留与降低权重差异"],
    ["确定性约束测算", "目标比例未必满足交易与现金条件", "数量取整、费用及现金约束后重新计算风险", "不足一手、现金预留及重复计算测试"],
    ["独立来源校验", "同源转载易被误计为多项证据", "统一口径，按来源谱系计数并保留冲突", "同源重复、独立反对及缺失来源测试"],
    ["输入版本核验", "连续对话可能沿用已变化的资料", "确认前提、版本与内容指纹共同约束请求", "持仓变化、旧修订及确认冲突测试"],
    ["双重审查与回执", "解释文本难以说明建议是否具备资格", "风险与合规独立判定，回执绑定输入和依据", "过期证据、跨用户及回执篡改测试"],
]
POINTS = [
    (
        "3.6.1 画像驱动的可计算风险约束",
        "系统将问卷形成的画像风险等级映射为单一资产、已识别行业、科技行业及未分类暴露的预算上限，"
        "并将预算绑定已确认的画像版本。组合暴露经过程序计算后，逐项输出观察比例、适用上限和超限幅度，"
        "个人风险条件由此成为测算过程中的实际约束。",
        "固定场景测试保持持仓与研究依据一致，仅改变画像风险等级，均衡型与保守型分别得到保留和降低权重的结构化结果。"
        "这说明个性化差异来自预算条件及计算结果，能够解释同一市场事实为何对不同投资者产生不同处理结论。"
        "对应实现见 3.4.2 节及图 3-9。",
    ),
    (
        "3.6.2 面向交易约束的确定性测算闭环",
        "LLM 负责理解问题、提取参数、选择工具和说明结果；金额、暴露、交易数量、费用及现金变化由确定性程序处理。"
        "再平衡先将目标比例转换为交易单位数量，再按卖出与买入顺序更新现金，最后以实际测算数量重新计算组合暴露和风险预算。",
        "该机制把目标配置与可测算数量之间的差异明确呈现出来。不足一个交易单位的减仓、无法覆盖费用或现金预留未满足时，"
        "结果保留复核状态及具体原因。数量、费用、现金和调整后风险采用同一组输入，用户可以复算关键步骤；"
        "相关边界及重复计算已由固定用例验证。对应实现见 3.4.3—3.4.4 节及图 3-10、图 3-11。",
    ),
    (
        "3.6.3 按来源独立性判定事实支持",
        "研究验证先统一主体、指标、单位和期间，再按来源谱系分组。同一来源的多个转载只计为一项独立依据；"
        "缺少来源关联、组内数值冲突或独立来源反对时，保留不足、冲突或待复核状态。"
        "研究证据、事实、发现与结构化建议之间继续保持明确的引用关系。",
        "这一机制将材料数量与独立支持程度分别处理，减少重复转载形成虚假共识的风险。"
        "自动化测试覆盖同源重复不增加独立支持数、独立反对不能被支持记录掩盖，以及缺失来源不能形成已验证事实。"
        "检索片段用于核对原文，金融声明仍按结构化口径校验。对应实现见 3.4.6—3.4.7 节及图 3-13、图 3-15。",
    ),
    (
        "3.6.4 输入版本约束下的持续有效性检查",
        "会话前提由服务端读取已确认画像、持仓与数据模式，以修订号和内容指纹形成确定的分析输入。"
        "后续请求同时核对用户归属、预期修订和当前事实；资料变化时停止沿用旧前提，提示重新确认。"
        "历史消息用于理解问题，显式恢复的历史资料经过确认后才参与新的计算。",
        "该机制将连续对话的语义记忆与当前金融事实分开管理，降低旧持仓或旧画像继续影响新分析的风险。"
        "测试验证了锁定后持仓变化触发漂移、旧修订被拒绝，以及确认过程中资料变化不能被旧请求覆盖。"
        "结论的适用范围能够随输入版本被检查。对应实现见 3.4.8 节及图 3-16、图 3-17。",
    ),
    (
        "3.6.5 独立双闸门与可追溯决策回执",
        "结构化建议分别接受风险和合规审查。风险审查检查画像、组合、预算与证据，合规审查检查用户归属、引用、披露及禁止表述；"
        "整体状态按阻断、复核、通过的优先顺序聚合，双方通过后才进入建议组合。"
        "组合阶段继续核对输入版本和引用，避免解释文本代替资格判定。",
        "决策回执绑定画像与持仓版本、研究依据、规则版本、审查结果及内容哈希，便于核查结论使用了哪些输入、哪些规则以及哪些证据。"
        "过期证据、跨用户输入、引用或回执内容篡改等场景已有阻断测试。"
        "研究、计算与输出审查由此形成可检查的责任关系。对应实现见 3.4.6 节及图 3-14。",
    ),
]
ENDING = (
    "上述机制共同提高个性化分析的可解释性、计算的可复核性和结论的可追溯性。"
    "本节对应的画像差异、来源验证、交易约束、会话前提及建议回执共 64 项定向自动化用例已通过。"
    "该验证说明程序机制及边界处理能够执行；数值算法继续采用 3.4.9 节所述成熟方法，实际投资收益不在本节验证范围内。"
)


def paragraph(template, text, *, keep_lines=False):
    node = etree.Element(f"{{{NS['w']}}}p")
    properties = template.find("w:pPr", NS)
    if properties is not None:
        node.append(deepcopy(properties))
    if keep_lines:
        cloned = node.find("w:pPr", NS)
        keep = cloned.find("w:keepLines", NS)
        if keep is None:
            keep = etree.SubElement(cloned, f"{{{NS['w']}}}keepLines")
        keep.set(f"{{{NS['w']}}}val", "1")
    run = etree.SubElement(node, f"{{{NS['w']}}}r")
    run_properties = template.find("w:r/w:rPr", NS)
    if run_properties is not None:
        run.append(deepcopy(run_properties))
    etree.SubElement(run, f"{{{NS['w']}}}t").text = text
    return node


def summary_table(template, rows=ROWS):
    table = deepcopy(template)
    source_rows = template.findall("w:tr", NS)
    for row in table.findall("w:tr", NS):
        table.remove(row)
    for index, values in enumerate(rows):
        row = deepcopy(source_rows[0 if index == 0 else 1])
        for cell, text in zip(row.findall("w:tc", NS), values, strict=True):
            source_paragraph = cell.find("w:p", NS)
            for child in list(cell):
                if child.tag != f"{{{NS['w']}}}tcPr":
                    cell.remove(child)
            cell.append(paragraph(source_paragraph, text))
        table.append(row)
    return table


def augment(source: Path, destination: Path, proof_path: Path, *, intro=INTRO, rows=ROWS,
            points=POINTS, ending=ENDING, caption="表 3-4 项目创新点与验证依据"):
    source_bytes = source.read_bytes()
    with ZipFile(source) as original:
        root = etree.fromstring(original.read("word/document.xml"))
        body = root.find("w:body", NS)
        originals = [etree.tostring(node) for node in body]
        headings = {"".join(node.xpath(".//w:t/text()", namespaces=NS)): node for node in body if node.tag.endswith("}p")}
        if "3.6 项目创新点" in headings:
            raise ValueError("Document already has an innovations section")
        chapter = headings["3.1 项目总体设计"]
        subheading = headings["3.4.2 投资者画像与风险预算映射"]
        prose = body[3]
        additions = [paragraph(chapter, "3.6 项目创新点"), paragraph(prose, intro, keep_lines=True),
                     summary_table(body[13], rows), paragraph(body[61], caption)]
        for heading, first, second in points:
            additions.extend([paragraph(subheading, heading), paragraph(prose, first, keep_lines=True),
                              paragraph(prose, second, keep_lines=True)])
        additions.append(paragraph(prose, ending, keep_lines=True))
        section = body.find("w:sectPr", NS)
        if section is not body[-1]:
            raise ValueError("Unexpected document section layout")
        insert_at = len(body) - 1
        for node in additions:
            body.insert(insert_at, node)
            insert_at += 1
        assert [etree.tostring(node) for node in list(body)[:len(originals)-1]] + [etree.tostring(body[-1])] == originals
        modified = etree.tostring(root, encoding="UTF-8", xml_declaration=True, standalone=True)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(destination, "w") as output:
            for info in original.infolist():
                output.writestr(info, modified if info.filename == "word/document.xml" else original.read(info))
    with ZipFile(source) as before, ZipFile(destination) as after:
        assert before.namelist() == after.namelist()
        assert after.testzip() is None
        changed = [name for name in before.namelist() if before.read(name) != after.read(name)]
        assert changed == ["word/document.xml"]
    assert source.read_bytes() == source_bytes
    proof = {"source": str(source), "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
             "output_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
             "changed_parts": changed, "preserved_original_body_elements": len(originals),
             "added_body_elements": len(additions), "added_summary_rows": len(rows), "added_points": len(points),
             "preserved_styles_headers_footers_media_relationships": True,
             "source_unchanged": True, "zip_crc": "PASS"}
    proof_path.parent.mkdir(parents=True, exist_ok=True)
    proof_path.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Added {len(points)} innovations; only document.xml changed: {destination}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--proof", type=Path, required=True)
    args = parser.parse_args()
    augment(args.input, args.output, args.proof)

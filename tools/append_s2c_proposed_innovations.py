"""Append explicitly unimplemented functional proposals without restyling the DOCX."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from zipfile import ZipFile

from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.augment_s2c_innovations import NS, paragraph, summary_table


INTRO = (
    "本节提出五项拟新增的功能创新，供下一阶段范围确认。各项目前均为技术方案，尚未实施，不计入第 3.6 节的已实现成果。"
    "建议优先建设自然语言研究方法生成与投资假设跟踪，使个人研究系统从手工配置进一步发展为可共创、可持续观察的研究助手；"
    "其余方向按数据条件与演示重点选取。"
)
ROWS = [
    ["拟新增功能", "用户获得的能力", "相对现有功能的增量", "建议次序"],
    ["自然语言创建研究方法", "描述想法并生成可编辑研究草稿", "由调用已有技能扩展为生成技能组合", "优先实施"],
    ["投资假设持续跟踪", "持续查看买入理由是否仍有依据", "由单次研究扩展为条件订阅与变化记录", "优先实施"],
    ["公告变化关联持仓", "了解新公告与自己的组合有何关系", "由资料查询扩展为账户相关事件分析", "第二批"],
    ["多策略模拟组合", "用相同资金和条件比较研究方法", "由单次方案对比扩展为连续模拟跟踪", "数据就绪后"],
    ["多目标资金规划", "统筹不同用途及期限的资金安排", "由目标权重扩展为未来现金需求规划", "按产品定位选择"],
]
POINTS = [
    (
        "3.7.1 自然语言创建研究方法",
        "拟允许用户描述研究想法，例如“用净利润除以营业收入，达到 15% 时提醒我”。系统生成资料助手、指标公式、观察条件及任务依赖草稿，"
        "以中文展示每个步骤，用户可继续要求修改阈值或更换数据技能，确认后保存为个人研究方法。该功能将现有手工配置与聊天调用连接起来，"
        "降低普通投资者建立自有指标体系的操作成本。",
        "技术上采用自然语言到受控研究定义的编译流程。LLM 只解析意图与生成结构化草稿，服务端检查技能权限、字段单位、公式及依赖，"
        "金融数值仍由确定性程序计算。首期仅开放现有比率、差值和加权平均算子，超出能力的描述返回具体缺口。"
        "演示验收拟采用“描述需求、预览草稿、修改参数、确认保存、实际运行”完整流程，确认前不得改变已保存系统。",
    ),
    (
        "3.7.2 投资假设持续跟踪",
        "拟把研究结论转为可持续跟踪的投资假设卡，记录观察理由、适用标的、关键指标、失效条件和下次复核时间。"
        "例如，用户将“盈利改善”具体化为连续两个报告期净利率上升；后续财报到达时，系统更新趋势、列出变化依据，并提醒重新研究。"
        "用户能够持续回答“当初的投资理由是否仍成立”，形成研究、观察和复盘的连续使用流程。",
        "拟新增假设版本、条件订阅和事件记录，复用个人研究系统与事实存储。发布时点和报告期分别处理，重复资料只触发一次研究；"
        "来源更正后重新计算并保留变化记录。监测频率、停止条件和提醒范围由用户确认，页面区分条件满足、条件不满足与资料不足。"
        "验收拟展示一份新增财报如何改变假设状态及解释，触发的是研究提醒，任何调仓计划仍需用户另行确认。",
    ),
    (
        "3.7.3 公告变化关联持仓",
        "拟将公司公告、财报修订与用户实际持仓连接，生成“这次变化与我有什么关系”的事件卡。系统先提取变化字段及原文，"
        "再查找直接持仓和基金披露中的间接持仓，展示相关资产、已披露敞口及可能需要复核的研究假设。"
        "用户可以从一条公告跳转到组合影响与对应研究方法，减少在资讯、基金持仓和个股页面之间反复查找。",
        "实现拟增加文档版本差异、实体匹配及持仓关联服务。数量和权重由程序汇总，同一持仓路径去重；基金披露日期、穿透层级与未覆盖比例明确展示，"
        "不将已披露部分外推为完整敞口。文本只能提出待核实关系，不能直接推导股价涨跌。演示拟以同一公司公告关联一笔直投和一只持有该公司的基金，"
        "展示敞口构成、资料日期及需要更新的假设；真实落地依赖可追溯公告和基金披露数据。",
    ),
    (
        "3.7.4 多策略模拟组合",
        "拟允许用户把多个个人研究方法连接到显式配置的模拟调仓规则，在相同初始资金、可选资产、费用和约束下并行观察。"
        "例如，将盈利质量观察与低换手风格分别用于两套虚拟组合，持续比较净值变化、回撤、换手及现金占用。"
        "指标到目标权重的规则须由用户确认，使研究指标能够进入可比较的组合实验。",
        "首期建议采用从启用日起记录的前向模拟，新增虚拟账本、价格日历及规则快照，复用确定性调仓服务。完整历史时点数据齐备后再增加历史回放，"
        "按当时可得资料计算，并处理复权、停牌及交易成本。数据缺口暂停相关组合，不以未来信息补齐。验收拟重放一段冻结事件序列，"
        "核对两套虚拟账本及费用差异；排名只描述给定条件下的表现，不据短期结果自动选择真实投资策略。",
    ),
    (
        "3.7.5 多目标资金规划",
        "拟支持用户将同一账户划分为应急储备、近期支出和长期投资等逻辑资金目标，分别设置金额、期限、优先级及已确认现金流。"
        "系统按时间排列资金需求，展示各目标可用资金与缺口；当近期支出提前或金额变化时，重新测算可用于长期投资的资金，"
        "并生成可审阅的调整方案。逻辑划分不代表开立新的证券账户。",
        "实现拟增加目标台账与时间分桶计算，明确每笔资金的归属，防止同一笔资产被多个目标重复占用。"
        "现金安排由确定性程序计算，并受账户整体画像、风险预算及已确认长期偏好约束。首期按已确认收支与明确情景规划，不给出未经模型验证的达标概率。"
        "演示拟将一项支出提前，展示期限缺口和调整方案如何同步变化；这使个性化从交易节奏进一步延伸到实际资金用途。",
    ),
]
PRIORITIES = (
    "建议将自然语言创建研究方法与投资假设跟踪作为第一批：两者直接延续个人技能与长期使用场景，可展示“表达想法、生成方法、持续观察”的完整过程。"
    "公告与持仓关联作为第二批，并复用假设跟踪的事件入口。多策略模拟需要明确规则与连续价格，多目标规划需要确认产品是否覆盖资金用途管理，"
    "可分别选取，不要求五项同时实施。"
)
ENDING = (
    "确认时可按功能选择，并进一步确定首期边界、数据来源和演示场景。未经确认，本节仅保留为候选技术方案，不启动功能开发、后台监测或策略运行。"
    "上述方向属于交互方式、研究流程和个性化应用的产品与工程创新，原创性及竞争优势仍需结合参赛要求与同类产品调研评估。"
)


def append_proposals(source, destination, proof_path):
    source_bytes = source.read_bytes()
    with ZipFile(source) as original:
        root = etree.fromstring(original.read("word/document.xml"))
        body = root.find("w:body", NS)
        originals = [etree.tostring(node) for node in body]
        headings = {"".join(n.xpath(".//w:t/text()", namespaces=NS)): n for n in body if n.tag.endswith("}p")}
        title = "3.7 拟新增功能创新方案"
        if title in headings:
            raise ValueError("Proposal section already exists")
        chapter = paragraph(headings["3.6 项目创新点"], title)
        etree.SubElement(chapter.find("w:pPr", NS), f"{{{NS['w']}}}pageBreakBefore")
        prose = body[3]
        subheading = headings["3.6.1 自定义技能与 Agent 组成个人研究系统"]
        additions = [chapter, paragraph(prose, INTRO, keep_lines=True), summary_table(body[13], ROWS),
                     paragraph(body[61], "表 3-5 拟新增功能与实施建议")]
        for heading, first, second in POINTS:
            additions.extend([paragraph(subheading, heading), paragraph(prose, first, keep_lines=True),
                              paragraph(prose, second, keep_lines=True)])
        additions.extend([paragraph(subheading, "3.7.6 实施顺序与确认范围"),
                          paragraph(prose, PRIORITIES, keep_lines=True), paragraph(prose, ENDING, keep_lines=True)])
        assert body[-1].tag == f"{{{NS['w']}}}sectPr"
        for node in additions:
            body.insert(len(body)-1, node)
        assert [etree.tostring(n) for n in list(body)[:len(originals)-1]] + [etree.tostring(body[-1])] == originals
        modified = etree.tostring(root, encoding="UTF-8", xml_declaration=True, standalone=True)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(destination, "w") as output:
            for info in original.infolist():
                output.writestr(info, modified if info.filename == "word/document.xml" else original.read(info))
    with ZipFile(source) as before, ZipFile(destination) as after:
        assert before.namelist() == after.namelist() and after.testzip() is None
        changed = [name for name in before.namelist() if before.read(name) != after.read(name)]
        assert changed == ["word/document.xml"]
        media_count = len([name for name in before.namelist() if name.startswith("word/media/")])
    assert source_bytes == source.read_bytes()
    proof = {"status": "PROPOSED_AWAITING_USER_CONFIRMATION", "application_changes": False,
             "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
             "output_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
             "changed_parts": changed, "preserved_body_elements": len(originals),
             "added_body_elements": len(additions), "proposals": len(POINTS), "preserved_media": media_count,
             "source_unchanged": True, "zip_crc": "PASS"}
    proof_path.parent.mkdir(parents=True, exist_ok=True)
    proof_path.write_text(json.dumps(proof, ensure_ascii=False, indent=2)+'\n', encoding="utf-8")
    print("PASS: five proposed innovations appended; original content and all other DOCX parts preserved")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--proof", type=Path, required=True)
    args = parser.parse_args()
    append_proposals(args.source, args.destination, args.proof)

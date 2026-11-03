"""Reclassify the five approved proposals using verified implementation boundaries."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from zipfile import ZipFile

from lxml import etree

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.augment_s2c_innovations import NS,paragraph,summary_table
from tools.append_s2c_proposed_innovations import INTRO as OLD_INTRO,POINTS as OLD_POINTS,PRIORITIES as OLD_PRIORITIES,ENDING as OLD_ENDING


INTRO=(
    "本节五项创新功能已连接正式前端、服务端执行与私有版本存储。自然语言创建研究方法、投资假设跟踪和公告持仓关联使研究能够持续开展；"
    "多策略模拟及资金用途规划把研究方法与个人组合、实际期限相连接。用户可以完成草稿确认、订阅管理、事件分析和组合实验，"
    "并在条件变化后修订自己的研究与资金安排。"
)
ROWS=[
    ["已实现功能","用户可以完成的任务","执行机制","功能入口"],
    ["自然语言创建研究方法","描述想法、修改草稿、保存个人技能","语义解析、受控指标定义与确认保存","研究工具"],
    ["投资假设持续跟踪","持续查看研究理由是否仍有依据","条件订阅、周期复核与变化记录","研究任务"],
    ["公告变化关联持仓","了解新资料与自身组合的关系","原文差异、直接和基金披露敞口","研究资料"],
    ["多策略模拟组合","按相同基线持续比较研究方法","规则目标、虚拟账本与独立风险判断","情景模拟"],
    ["多目标资金规划","统筹资金用途、期限及确认现金流","时间分配、缺口及受约束调整测算","调仓方案"],
]
POINTS=[
    (
        "3.7.1 自然语言创建研究方法",
        "用户描述研究想法后，系统生成资料助手、指标公式、观察条件及任务依赖草稿，并以中文展示各项职责。"
        "用户可以追问修改阈值、更改方法名称，或载入最近草稿继续编辑，确认后保存为自己的研究技能。"
        "例如，“净利润除以营业收入，达到 15% 时提醒我”形成可运行的盈利质量观察方法，后续可以在页面与 AI 投资助手中复用。",
        "语义规则可直接解析净利率及百分比条件；其他描述使用已配置模型生成受控定义，未配置或超出能力时显示具体缺口。"
        "服务端检查技能权限、字段、单位与指标依赖，当前支持比率、差值和加权平均。模型只负责意图与草稿，金融计算仍由程序执行。"
        "生成草稿不会修改已保存系统，明确确认后才产生可执行版本，形成描述、编辑、保存和运行的完整流程。",
    ),
    (
        "3.7.2 投资假设持续跟踪",
        "投资者可以把研究理由保存为假设卡，绑定个人方法、标的、指标、报告期和复核周期。"
        "系统支持阈值观察，以及按三个指定报告期检查两次上升或下降；结果区分条件成立、不成立和资料不足。"
        "启用的跟随订阅在当前账户可访问的新财报进入资料库后更新观察期，并保留状态变化，使用户能够持续复核当初的投资理由。",
        "订阅须明确确认，默认每 24 小时复核，可立即检查或停止；同一内容不重复记为新变化。"
        "资料公开时点与报告期分别处理，方法变更或工具停用后不生成有效结论。监测复用全局研究准入，每次包含等待的总预算为 60 秒，"
        "停止及服务关闭会传播取消。该功能产生的是研究状态和页面提醒，调仓仍需另外测算和确认。",
    ),
    (
        "3.7.3 公告变化关联持仓",
        "公司公告或财报可与当前服务端持仓关联。事件卡显示版本间的原文变化、直接持仓、基金披露中的间接路径以及需要复核的同标的假设。"
        "用户可直接理解“这次资料变化与我的组合有什么关系”，并查看原文位置和披露日期。"
        "在受控样例中，直接持仓 1 万元，另持有 1 万元基金且该公司披露权重为 10%，程序得到已知关联敞口 1.1 万元。",
        "金额与权重沿用确定性穿透计算，路径保留持仓和基金快照引用，未披露部分单列。"
        "该样例总组合为 2 万元，已知敞口为 55%，剩余 9 千元不外推为该公司的持仓。"
        "资料必须具有明确证券代码及已发布时点，更正或删除使旧事件引用失效。原文关系用于研究关联，不能直接推导股价涨跌。",
    ),
    (
        "3.7.4 多策略模拟组合",
        "用户可将个人研究指标连接到已确认的条件和目标比例，在相同初始持仓、资金、费用及风险条件下比较虚拟组合。"
        "每次推进实际执行研究，并使用当前可信报价计算数量、现金、累计费用、换手和回撤；页面区分已模拟成交、保持持仓及需要复核。"
        "首期支持当前组合中的股票、ETF 整数持仓和人民币现金，页面配置两套策略，结构化接口最多支持五套。",
        "在 10 万元受控基线中，资产 A 为 2,000 股、每股 10 元，其他五项各 1.3 万元，现金 1.5 万元。"
        "盈利指标达到第一套规则后，虚拟减持 1,000 股，费用为 10.10 元，权益为 99,989.90 元；第二套规则未满足，保留 100,000 元。"
        "交易后体检和完整风险预算分别检查，任一未通过不改变虚拟数量或现金。记录从启用后向前推进，历史回测及长期投资有效性尚未验收，真实账户不会被模拟更新。",
    ),
    (
        "3.7.5 多目标资金规划",
        "用户可以按应急、近期支出或长期用途保存资金目标，设置金额、需求日期和同日优先级，并登记已确认收入与支出。"
        "程序在一个现金池中按日期分配资金，展示各目标已分配金额、期限缺口及剩余现金；金额、日期或现金流修订后形成新版本并重新测算。"
        "逻辑用途划分不会开立新的证券账户，也不会让同一笔资产同时支持多个目标。",
        "例如，当前现金 3 万元，近期目标需要 4 万元，而 2 万元确认收入在更晚日期到达，近期仍保留 1 万元缺口；该收入只在后续日期参与分配。"
        "调整方案绑定当前组合、已确认画像与可用长期风格，金额和费用沿用确定性调仓程序。系统只增加所需预留，不因目标减少自动降低当前现金比例；"
        "费用、风险或总资金不足时保留复核及缺口，不假设资产收益或生成未经验证的达标概率。",
    ),
]
PRIORITIES=(
    "五项功能已形成正式操作入口和可持久保存的执行记录，修改采用预期版本检查，账户权限由服务端认证上下文绑定。"
    "自然语言方法连接个人技能，假设持续跟踪使用其指标，公告事件关联同标的假设，模拟与资金规划复用组合及调仓计算。"
    "画像、政策、行情或研究方法变化后，相关结果显示历史失效或要求新建实验，支持用户在长期使用中持续修订方法。"
)
ENDING=(
    "本次实现的全量自动化验证为 1,235 项通过、1 项跳过，含真实本机 PostgreSQL；五页在三种固定视口的 15 组布局检查通过。"
    "上述数值案例为受控功能验证，不作为实盘收益证明。真实模型语义质量、上游财报与基金披露覆盖、完整历史回测及长期策略效果需独立验收。"
)


def finalize(source,destination,proof_path):
    source_bytes=source.read_bytes()
    with ZipFile(source) as original:
        root=etree.fromstring(original.read('word/document.xml'))
        body=root.find('w:body',NS)
        text=lambda node:''.join(node.xpath('.//w:t/text()',namespaces=NS))
        mapping={'3.7 拟新增功能创新方案':'3.7 已实现创新功能扩展',OLD_INTRO:INTRO,
                 '表 3-5 拟新增功能与实施建议':'表 3-5 已实现创新功能与产品入口',
                 '3.7.6 实施顺序与确认范围':'3.7.6 集成结果与验证范围',OLD_PRIORITIES:PRIORITIES,OLD_ENDING:ENDING}
        for old,new in zip(OLD_POINTS,POINTS):
            mapping.update(zip(old,new))
        changed=0
        for node in list(body):
            if node.tag.endswith('}p') and text(node) in mapping:
                replacement=paragraph(node,mapping[text(node)])
                body.replace(node,replacement)
                changed+=1
            elif node.tag.endswith('}tbl') and '拟新增功能' in text(node):
                body.replace(node,summary_table(node,ROWS))
        assert changed==len(mapping),(changed,len(mapping))
        content=''.join(root.xpath('//w:t/text()',namespaces=NS))
        assert '拟新增功能创新方案' not in content and '未经确认，本节' not in content
        modified=etree.tostring(root,encoding='UTF-8',xml_declaration=True,standalone=True)
        destination.parent.mkdir(parents=True,exist_ok=True)
        with ZipFile(destination,'w') as output:
            for info in original.infolist():
                output.writestr(info,modified if info.filename=='word/document.xml' else original.read(info))
    with ZipFile(source) as before,ZipFile(destination) as after:
        changed_parts=[n for n in before.namelist() if before.read(n)!=after.read(n)]
        assert before.namelist()==after.namelist() and changed_parts==['word/document.xml'] and after.testzip() is None
        media=len([n for n in before.namelist() if n.startswith('word/media/')])
    assert source.read_bytes()==source_bytes
    proof_path.parent.mkdir(parents=True,exist_ok=True)
    proof={'source_sha256':sha256(source_bytes).hexdigest(),'output_sha256':sha256(destination.read_bytes()).hexdigest(),
           'classification':'IMPLEMENTED_AUTOMATED_VALIDATION_COMPLETE','changed_parts':changed_parts,'changed_paragraphs':changed,
           'preserved_media_count':media,'source_unchanged':True,'zip_crc':'PASS'}
    proof_path.write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('PASS: five innovations reclassified with implemented scope; original design and media preserved')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('destination',type=Path)
    parser.add_argument('--proof',type=Path,required=True)
    args=parser.parse_args()
    finalize(args.source,args.destination,args.proof)

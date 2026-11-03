"""Natural-language intent becomes a preview; only user confirmation saves a skill."""
import json
import re
from uuid import uuid4

from pydantic import Field

from app.service.personal_research import _Model, PersonalResearchDefinition, PersonalResearchSave, profitability_template
from app.service.research_lab_store import LabInvalid


class MethodDraftInput(_Model):
    prompt: str = Field(min_length=3, max_length=2000)
    draft_id: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9_-]{0,79}$")
    expected_revision: int = Field(default=0, ge=0)


class MethodConfirmInput(_Model):
    expected_revision: int = Field(ge=1)
    system_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,79}$")
    expected_system_revision: int = Field(default=0, ge=0)
    definition: PersonalResearchDefinition | None = None


class MethodBuilder:
    def __init__(self, records, personal, client=None):
        self.records, self.personal, self.client = records, personal, client

    def _local(self, owner, text, previous=None):
        threshold = re.search(r"(?:达到|不低于|至少|阈值|改为|改成|调整为|不超过|不高于)\s*(?:为)?\s*(-?\d+(?:\.\d+)?)\s*[%％]", text)
        if previous and threshold and not any(word in text for word in ("除以", "减去", "加权")):
            definition = json.loads(json.dumps(previous))
            if not definition["observers"]:
                return None
        elif ("净利率" in text or ("净利润" in text and "营业收入" in text and ("除以" in text or "比率" in text))) and threshold:
            definition = profitability_template().model_dump(mode="json")
        else:
            return None
        for observer in definition["observers"]:
            observer.update(threshold=threshold.group(1), comparison="lte" if any(w in text for w in ("不超过", "不高于")) else "gte",
                            matched_message="达到已确认的研究条件，请查看计算资料。", unmatched_message="未达到已确认的研究条件。")
        available = [s for s in self.personal.catalog(owner)["skills"] if s["operation"] == "COMPANY_DATA" and s["callable"]]
        if not available:
            raise LabInvalid("尚无可调用的财务资料技能，请先选择并启用工具。")
        for agent in definition["data_agents"]:
            agent.update(skill_id=available[0]["skill_id"], version=available[0]["version"])
        return definition

    async def generate(self, owner, body):
        previous = None
        if body.draft_id:
            row = self.records.get(owner, "method", body.draft_id)
            if row["revision"] != body.expected_revision or row["payload"]["status"] != "DRAFT":
                raise LabInvalid("草稿已变化或已经保存，请重新创建。")
            previous = row["payload"]["definition"]
        elif body.expected_revision:
            raise LabInvalid("新草稿修订应为零。")
        definition = self._local(owner, body.prompt, previous)
        mode = "DETERMINISTIC_INTENT_RULES"
        if definition is None:
            client = self.client() if callable(self.client) else self.client
            if client is None or not client.is_configured:
                raise LabInvalid("当前可直接解析净利率与百分比阈值；其他研究描述需要已配置模型，或使用手工指标配置。")
            async def operation():
                nonlocal definition
                catalog = self.personal.catalog(owner)
                tool = {"type": "function", "function": {"name": "preview_research_definition", "description": "只生成待确认定义，不执行或保存。", "parameters": PersonalResearchDefinition.model_json_schema()}}
                messages = [{"role": "system", "content": "仅从目录中选择可调用技能、字段及三个支持算子，生成研究定义草稿。不得添加owner、代码、URL、金融计算结果。资料不足不得猜测。目录："+json.dumps(catalog, ensure_ascii=False)},
                            {"role": "user", "content": json.dumps({"prompt":body.prompt,"previous_draft":previous}, ensure_ascii=False)}]
                async with self.personal.runtime.model_slot():
                    async for event in client.stream_chat(messages, tools=[tool], tool_choice="auto"):
                        if event.get("type") == "tool_call" and event.get("name") == "preview_research_definition":
                            if definition is not None:
                                raise LabInvalid("模型返回多个不一致草稿，请重新描述。")
                            definition = event.get("arguments")
                if definition is None:
                    raise LabInvalid("模型未生成有效的研究草稿。")
                return {"status":"COMPLETED"}
            await self.personal.runtime.run(owner, operation, budget_seconds=20)
            mode = "MODEL_INTENT_ONLY"
        checked = PersonalResearchDefinition.model_validate(definition)
        self.personal._validate_skills(owner, checked, require_callable=True)
        return self.records.write(owner, "method", body.draft_id or uuid4().hex, body.expected_revision,
            {"name":checked.name,"prompt":body.prompt,"definition":checked.model_dump(mode="json"),"status":"DRAFT","generation_mode":mode,
             "notice":"仅为可编辑草稿，确认保存后才能作为个人研究技能使用。"})

    def confirm(self, owner, draft_id, body):
        with self.records.store._lock:
            draft = self.records.get(owner, "method", draft_id)
            if draft["revision"] != body.expected_revision or draft["payload"]["status"] != "DRAFT":
                raise LabInvalid("草稿已变化或已经保存。")
            definition = body.definition or PersonalResearchDefinition.model_validate(draft["payload"]["definition"])
            self.personal._validate_skills(owner, definition, require_callable=True)
            saved = self.personal.save(owner, body.system_id, PersonalResearchSave(definition=definition, expected_revision=body.expected_system_revision))
            self.records.write(owner,"method",draft_id,body.expected_revision,{**draft["payload"],"definition":definition.model_dump(mode='json'),"name":definition.name,"status":"CONFIRMED","system_id":saved["system_id"],"system_revision":saved["revision"]})
            return saved

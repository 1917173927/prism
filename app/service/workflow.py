"""Editable DAG dependencies over the reviewed, closed research-node catalog."""
from __future__ import annotations
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.research import ResearchSpecialistMatrix


class WorkflowNode(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    node_id: str = Field(min_length=1, max_length=160)
    dependencies: tuple[str, ...] = Field(default=(), max_length=32)
    x: float = Field(default=0, ge=0, le=5000)
    y: float = Field(default=0, ge=0, le=5000)


class WorkflowDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["workflow-definition.v1"] = "workflow-definition.v1"
    owner_id: str = Field(min_length=1, max_length=160)
    nodes: tuple[WorkflowNode, ...] = Field(min_length=4, max_length=32)
    budget_ms: int = Field(default=3000, ge=100, le=10000)


class WorkflowSaveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    definition: WorkflowDefinition
    expected_revision: int = Field(ge=0)


class WorkflowRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)


def default_workflow(matrix):
    return WorkflowDefinition(owner_id=matrix.owner_id, budget_ms=matrix.budget_ms,
        nodes=tuple(WorkflowNode(node_id=n.node_id, dependencies=n.dependencies,
                                x=30 + (i % 4) * 235, y=40 + (i // 4) * 140) for i, n in enumerate(matrix.nodes)))


def bind_workflow(definition, matrix):
    if definition.owner_id != matrix.owner_id:
        raise ValueError("workflow owner mismatch")
    by_id = {node.node_id:node for node in definition.nodes}
    if len(by_id) != len(definition.nodes) or set(by_id) != {node.node_id for node in matrix.nodes}:
        raise ValueError("workflow must use each catalog node exactly once")
    # Sources, operations, evidence fields and validation rules remain server-owned.
    nodes = [{**node.model_dump(mode="python"), "dependencies":tuple(sorted(by_id[node.node_id].dependencies))}
             for node in matrix.nodes]
    return ResearchSpecialistMatrix.model_validate({**matrix.model_dump(mode="python"),
        "budget_ms":definition.budget_ms, "nodes":nodes})

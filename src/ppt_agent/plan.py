from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .models import OPERATIONS


@dataclass
class PlanStep:
    backend: Literal["engine", "wps"]
    operations: list[dict[str, Any]]
    order: int


@dataclass
class ExecutionPlan:
    """有序执行计划 + 批次最终 Postcondition。

    - steps：连续同类 operation 合并为一个执行单元，跨后端按声明顺序排列。
    - transition_expectations：reducer 推出的最终切换意图（slide -> spec），
      供 OOXML 恢复与最终验证使用；`none` 与 `set_transition` 会清除旧意图。
    """

    steps: list[PlanStep] = field(default_factory=list)
    transition_expectations: dict[int, dict[str, Any]] = field(default_factory=dict)

    @property
    def last_backend(self) -> str | None:
        return self.steps[-1].backend if self.steps else None


def build_execution_plan(operations: list[dict[str, Any]]) -> ExecutionPlan:
    plan = ExecutionPlan()
    transitions: dict[int, dict[str, Any] | None] = {}
    for operation in operations:
        spec = OPERATIONS[operation["op"]]
        if plan.steps and plan.steps[-1].backend == spec.backend:
            plan.steps[-1].operations.append(operation)
        else:
            plan.steps.append(PlanStep(backend=spec.backend, operations=[operation], order=len(plan.steps)))
        if spec.reducer is not None:
            spec.reducer(transitions, operation)
    plan.transition_expectations = {
        slide: transition for slide, transition in transitions.items() if transition is not None
    }
    return plan

from __future__ import annotations

from ppt_agent.models import OPERATIONS, OPERATION_GUIDE, OPERATION_MODELS, OPERATION_USE_WHEN
from ppt_agent.plan import build_execution_plan
from ppt_agent.service import STANDARD_OPS, WPS_OPS


def test_plan_batches_consecutive_same_backend_and_preserves_order() -> None:
    plan = build_execution_plan([
        {"op": "set_text", "object": "s0:s2", "text": "first"},
        {"op": "set_style", "object": "s0:s2", "font_size": 28},
        {"op": "set_transition", "slide": 1, "transition": "fade"},
        {"op": "add_animation", "object": "s0:s5", "effect": "fade"},
        {"op": "move", "object": "s0:s5", "x": 1.0, "y": 1.0},
    ])

    assert [(step.backend, [op["op"] for op in step.operations]) for step in plan.steps] == [
        ("engine", ["set_text", "set_style"]),
        ("wps", ["set_transition", "add_animation"]),
        ("engine", ["move"]),
    ]
    assert plan.last_backend == "engine"
    assert [step.order for step in plan.steps] == [0, 1, 2]


def test_plan_transition_reducer_push_none_push() -> None:
    plan = build_execution_plan([
        {"op": "set_slide", "slide": 0, "transition": {"type": "push", "dir": "l"}},
        {"op": "set_slide", "slide": 0, "transition": "none"},
        {"op": "set_slide", "slide": 0, "transition": {"type": "push", "dir": "r"}},
    ])
    assert plan.transition_expectations == {0: {"type": "push", "dir": "r"}}


def test_plan_transition_reducer_none_clears() -> None:
    plan = build_execution_plan([
        {"op": "set_slide", "slide": 0, "transition": {"type": "push", "dir": "l"}},
        {"op": "set_slide", "slide": 0, "transition": "none"},
    ])
    assert plan.transition_expectations == {}


def test_plan_transition_reducer_wps_set_transition_clears() -> None:
    plan = build_execution_plan([
        {"op": "set_slide", "slide": 0, "transition": {"type": "push", "dir": "l"}},
        {"op": "set_transition", "slide": 0, "transition": "fade"},
    ])
    assert plan.transition_expectations == {}


def test_plan_transition_reducer_ignores_unrelated_set_slide() -> None:
    plan = build_execution_plan([
        {"op": "set_slide", "slide": 0, "background": "FFFFFF"},
        {"op": "set_slide", "slide": 0, "hidden": True},
    ])
    assert plan.transition_expectations == {}


def test_registry_derives_models_guide_and_backends() -> None:
    assert len(OPERATIONS) == 26
    assert set(OPERATION_MODELS) == set(OPERATIONS)
    assert set(OPERATION_GUIDE) == set(OPERATIONS)
    assert set(OPERATION_USE_WHEN) == set(OPERATIONS)
    assert WPS_OPS == {"add_animation", "set_transition", "set_chart_title"}
    assert STANDARD_OPS | WPS_OPS == set(OPERATIONS)
    assert not (STANDARD_OPS & WPS_OPS)


def test_registry_examples_validate_and_wps_flag_matches_backend() -> None:
    for name, spec in OPERATIONS.items():
        operation = spec.model.model_validate(spec.example)
        assert operation.op == name
        assert spec.backend in {"engine", "wps"}
        assert OPERATION_GUIDE[name]["wps"] == (spec.backend == "wps")
        assert spec.errors
        assert spec.use_when

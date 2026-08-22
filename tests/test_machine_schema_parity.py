from __future__ import annotations

import jsonschema
import pytest
from pydantic import ValidationError

from ppt_agent.models import (
    AddPictureOperation,
    AddShapeOperation,
    AddTableOperation,
    GradientSpec,
    MoveOperation,
    OPERATION_GUIDE,
    OPERATION_MODELS,
    ParagraphSpec,
    ReplaceTextOperation,
    ResizeOperation,
    SetPropsOperation,
    SetSlideOperation,
    SetStyleOperation,
    SetThemeOperation,
    SwapImageOperation,
    TransitionSpec,
)

# 协议规则：可选字段显式传 null 与省略等价。Pydantic 校验器全部按 `is None`
# 判断；机器 Schema 相应用值约束（type null / not null）而非存在性约束。
# 无法用标准 JSON Schema 表达的约束（如 add_table.fills 矩阵同形）不进入
# parity 样例，仍由 Pydantic 与 OPERATION_GUIDE.errors 兜底。

VALIDATOR_CASES: list[tuple[type, dict, bool]] = [
    # MoveOperation：x/y 与 dx/dy 二选一，且必须完整、非空
    (MoveOperation, {"op": "move", "object": "s0:s2", "x": 1.0, "y": 0.5}, True),
    (MoveOperation, {"op": "move", "object": "s0:s2", "dx": 0.25, "dy": 0.0}, True),
    (MoveOperation, {"op": "move", "object": "s0:s2"}, False),
    (MoveOperation, {"op": "move", "object": "s0:s2", "x": None, "y": None}, False),
    (MoveOperation, {"op": "move", "object": "s0:s2", "x": None, "y": 0.5}, False),
    (MoveOperation, {"op": "move", "object": "s0:s2", "x": 1.0, "y": 0.5, "dx": 0.25, "dy": 0.0}, False),
    # ResizeOperation：width/height 与 scale 二选一，且必须完整、非空
    (ResizeOperation, {"op": "resize", "object": "s0:s2", "width": 4.0, "height": 1.5}, True),
    (ResizeOperation, {"op": "resize", "object": "s0:s2", "scale": 0.8}, True),
    (ResizeOperation, {"op": "resize", "object": "s0:s2"}, False),
    (ResizeOperation, {"op": "resize", "object": "s0:s2", "width": None, "height": None}, False),
    (ResizeOperation, {"op": "resize", "object": "s0:s2", "width": 4.0, "height": 1.5, "scale": 0.8}, False),
    # SetPropsOperation：至少一个非空属性
    (SetPropsOperation, {"op": "set_props", "title": "t"}, True),
    (SetPropsOperation, {"op": "set_props"}, False),
    (SetPropsOperation, {"op": "set_props", "title": None}, False),
    # SetSlideOperation：至少一个非空变更
    (SetSlideOperation, {"op": "set_slide", "slide": 0, "hidden": True}, True),
    (SetSlideOperation, {"op": "set_slide", "slide": 0, "background": "FFFFFF"}, True),
    (SetSlideOperation, {"op": "set_slide", "slide": 0, "transition": "none"}, True),
    (SetSlideOperation, {"op": "set_slide", "slide": 0, "transition": {"type": "fade"}}, True),
    (SetSlideOperation, {"op": "set_slide", "slide": 0}, False),
    (SetSlideOperation, {"op": "set_slide", "slide": 0, "hidden": None}, False),
    (SetSlideOperation, {"op": "set_slide", "slide": 0, "background": None}, False),
    (SetSlideOperation, {"op": "set_slide", "slide": 0, "transition": None}, False),
    # SetStyleOperation：至少一个非空样式字段
    (SetStyleOperation, {"op": "set_style", "object": "s0:s2", "font_size": 32}, True),
    (SetStyleOperation, {"op": "set_style", "object": "s0:s2", "fill": "none"}, True),
    (SetStyleOperation, {"op": "set_style", "object": "s0:s2"}, False),
    (SetStyleOperation, {"op": "set_style", "object": "s0:s2", "font_size": None}, False),
    # AddShapeOperation：line 与非 line 几何互斥；null 等同省略
    (AddShapeOperation, {"op": "add_shape", "slide": 0, "kind": "line", "from": [0, 0], "to": [5, 5]}, True),
    (AddShapeOperation, {"op": "add_shape", "slide": 0, "kind": "line", "from": [0, 0], "to": [5, 5], "x": None}, True),
    (AddShapeOperation, {"op": "add_shape", "slide": 0, "kind": "line", "from": [0, 0], "to": [5, 5], "text": None}, True),
    (AddShapeOperation, {"op": "add_shape", "slide": 0, "kind": "line", "from": [0, 0], "to": [5, 5], "text": "x"}, False),
    (AddShapeOperation, {"op": "add_shape", "slide": 0, "kind": "line", "from": [0, 0], "to": [5, 5], "x": 1.0}, False),
    (AddShapeOperation, {"op": "add_shape", "slide": 0, "kind": "textbox", "x": 1, "y": 2, "width": 4, "height": 1.5}, True),
    (AddShapeOperation, {"op": "add_shape", "slide": 0, "kind": "textbox", "x": 1, "y": 2, "width": 4, "height": 1.5, "from": None}, True),
    (AddShapeOperation, {"op": "add_shape", "slide": 0, "kind": "textbox", "x": 1, "y": 2, "width": 4, "height": 1.5, "from": [0, 0], "to": [5, 5]}, False),
    (AddShapeOperation, {"op": "add_shape", "slide": 0, "kind": "textbox", "x": None, "y": 2, "width": 4, "height": 1.5}, False),
    # TransitionSpec：null 等同省略；dir/orient 按类型取值
    (TransitionSpec, {"type": "fade"}, True),
    (TransitionSpec, {"type": "fade", "dir": None, "orient": None}, True),
    (TransitionSpec, {"type": "push", "dir": None}, True),
    (TransitionSpec, {"type": "push", "dir": "l"}, True),
    (TransitionSpec, {"type": "fade", "dir": "l"}, False),
    (TransitionSpec, {"type": "split", "orient": "horz", "dir": "in"}, True),
    (TransitionSpec, {"type": "split", "dir": "l"}, False),
    # ParagraphSpec：text/runs 互斥；runs 非空
    (ParagraphSpec, {"text": "one"}, True),
    (ParagraphSpec, {"runs": [{"text": "a"}]}, True),
    (ParagraphSpec, {"text": None}, False),
    (ParagraphSpec, {"runs": None}, False),
    (ParagraphSpec, {"runs": []}, False),
    (ParagraphSpec, {"text": "one", "runs": [{"text": "a"}]}, False),
    # SwapImageOperation 三目标
    (SwapImageOperation, {"op": "swap_image", "object": "s0:s4", "image": "x.png"}, True),
    (SwapImageOperation, {"op": "swap_image", "media": "image1.png", "image": "x.png"}, True),
    (SwapImageOperation, {"op": "swap_image", "rid": "rId3", "slide": 0, "image": "x.png"}, True),
    (SwapImageOperation, {"op": "swap_image", "image": "x.png", "object": None}, False),
    (SwapImageOperation, {"op": "swap_image", "object": "s0:s4", "media": "image1.png", "image": "x.png"}, False),
    # SetThemeOperation
    (SetThemeOperation, {"op": "set_theme", "colors": {"accent1": "BB7B19"}}, True),
    (SetThemeOperation, {"op": "set_theme", "colors": {}}, False),
    (SetThemeOperation, {"op": "set_theme", "colors": {}, "fonts": {"major": "Georgia"}}, True),
    (SetThemeOperation, {"op": "set_theme", "colors": None, "fonts": None}, False),
    # AddTableOperation（可表达部分：行数/列宽计数不进入样例）
    (AddTableOperation, {"op": "add_table", "slide": 0, "at": [0, 0], "size": [9, 3], "rows": []}, False),
    (AddTableOperation, {"op": "add_table", "slide": 0, "at": [0, 0], "size": [9, 3], "rows": [["A", "B"], ["1", "2"]]}, True),
    # AddPictureOperation：width/height/size 最多一种
    (AddPictureOperation, {"op": "add_picture", "slide": 0, "image": "x.png", "at": [1, 2], "width": 2.0}, True),
    (AddPictureOperation, {"op": "add_picture", "slide": 0, "image": "x.png", "at": [1, 2], "width": 2.0, "height": 2.0}, False),
    (AddPictureOperation, {"op": "add_picture", "slide": 0, "image": "x.png", "at": [1, 2], "width": 2.0, "size": [4, 3]}, False),
    # ReplaceTextOperation：scope=slide 必须带 slide
    (ReplaceTextOperation, {"op": "replace_text", "from": "a", "to": "b", "scope": "deck"}, True),
    (ReplaceTextOperation, {"op": "replace_text", "from": "a", "to": "b", "scope": "slide"}, False),
    (ReplaceTextOperation, {"op": "replace_text", "from": "a", "to": "b", "scope": "slide", "slide": 0}, True),
    # GradientSpec：恰好两种颜色
    (GradientSpec, {"colors": ["112233", "445566"], "angle": 45}, True),
    (GradientSpec, {"colors": ["112233"]}, False),
]

# 每个 operation 的文档示例 + 逐字段删除/置 null/未知字段变异
MUTATION_CASES: list[tuple[type, dict, None]] = []
for operation_name, model in OPERATION_MODELS.items():
    example = OPERATION_GUIDE[operation_name]["example"]
    MUTATION_CASES.append((model, example, None))
    for key in list(example):
        deleted = {k: v for k, v in example.items() if k != key}
        MUTATION_CASES.append((model, deleted, None))
    for key in list(example):
        nulled = dict(example)
        nulled[key] = None
        MUTATION_CASES.append((model, nulled, None))
    with_extra = dict(example)
    with_extra["__unknown_field__"] = True
    MUTATION_CASES.append((model, with_extra, None))


def _pydantic_accepts(model: type, payload: dict) -> bool:
    try:
        model.model_validate(payload)
    except ValidationError:
        return False
    return True


def _schema_accepts(schema: dict, payload: dict) -> bool:
    try:
        jsonschema.Draft202012Validator(schema).validate(payload)
    except jsonschema.ValidationError:
        return False
    return True


ALL_CASES: list[tuple[type, dict, bool | None]] = [
    *VALIDATOR_CASES,
    *MUTATION_CASES,
]


@pytest.mark.parametrize("model", sorted(set(model for model, _, _ in ALL_CASES), key=lambda m: m.__name__))
def test_machine_schema_is_valid_draft2020(model: type) -> None:
    jsonschema.Draft202012Validator.check_schema(model.model_json_schema())


@pytest.mark.parametrize(("model", "payload", "expected"), ALL_CASES)
def test_machine_schema_and_pydantic_agree(model: type, payload: dict, expected: bool | None) -> None:
    schema = model.model_json_schema()
    pydantic_result = _pydantic_accepts(model, payload)
    schema_result = _schema_accepts(schema, payload)
    assert schema_result == pydantic_result, (
        f"parity broken for {model.__name__}: {payload}\n"
        f"pydantic={pydantic_result} schema={schema_result}"
    )
    if expected is not None:
        assert pydantic_result == expected

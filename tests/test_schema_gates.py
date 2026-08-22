from __future__ import annotations

import pytest
from pydantic import ValidationError

from ppt_agent.models import (
    SCHEMA_VERSION,
    AddShapeOperation,
    AddTableOperation,
    ParagraphSpec,
    SetThemeOperation,
    SwapImageOperation,
    TransitionSpec,
)


def _validates(model, payload: dict) -> None:
    model.model_validate(payload)  # must not raise


def _rejects(model, payload: dict) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(payload)


# machine JSON Schema must express the tightened constraints -------------------

def test_schema_version_and_package_version_bumped() -> None:
    from ppt_agent import __version__

    assert SCHEMA_VERSION == "2.1"
    assert __version__ == "0.2.4b1"


def test_swap_image_schema_expresses_target_oneof() -> None:
    schema = SwapImageOperation.model_json_schema()
    assert schema["oneOf"] == [
        {
            "required": ["object"],
            "properties": {
                "object": {"type": "string", "pattern": "^s\\d+:(?:s|o)\\d+$"},
                "media": {"type": "null"},
                "rid": {"type": "null"},
            },
        },
        {
            "required": ["media"],
            "properties": {
                "media": {"type": "string", "minLength": 1},
                "object": {"type": "null"},
                "rid": {"type": "null"},
            },
        },
        {
            "required": ["rid", "slide"],
            "properties": {
                "rid": {"type": "string", "minLength": 1},
                "slide": {"type": "integer", "minimum": 0},
                "object": {"type": "null"},
                "media": {"type": "null"},
            },
        },
    ]


def test_paragraph_schema_expresses_text_runs_oneof_and_min_runs() -> None:
    schema = ParagraphSpec.model_json_schema()
    assert schema["oneOf"] == [
        {
            "required": ["text"],
            "properties": {"text": {"type": "string"}, "runs": {"type": "null"}},
        },
        {
            "required": ["runs"],
            "properties": {"runs": {"type": "array", "minItems": 1}, "text": {"type": "null"}},
        },
    ]
    runs_schema = schema["properties"]["runs"]
    assert runs_schema["anyOf"][0]["minItems"] == 1


def test_transition_schema_expresses_per_type_rules() -> None:
    schema = TransitionSpec.model_json_schema()
    rules = schema["allOf"]
    fade_rule = next(rule for rule in rules if rule["if"]["properties"]["type"]["const"] == "fade")
    assert {"properties": {"dir": {"type": "null"}}} in fade_rule["then"]["allOf"]
    assert {"properties": {"orient": {"type": "null"}}} in fade_rule["then"]["allOf"]
    push_rule = next(rule for rule in rules if rule["if"]["properties"]["type"]["const"] == "push")
    assert {"properties": {"dir": {"anyOf": [{"type": "null"}, {"enum": ["l", "r", "u", "d"]}]}}} in push_rule["then"]["allOf"]


def test_add_shape_schema_expresses_line_geometry_rule() -> None:
    schema = AddShapeOperation.model_json_schema()
    rule = schema["allOf"][0]
    assert rule["if"] == {"properties": {"kind": {"const": "line"}}, "required": ["kind"]}
    then = rule["then"]
    assert then["required"] == ["from", "to"]
    assert then["properties"]["from"] == {"not": {"type": "null"}}
    assert then["properties"]["to"] == {"not": {"type": "null"}}
    for key in ("text", "x", "y", "width", "height"):
        assert then["properties"][key] == {"type": "null"}
    else_branch = rule["else"]
    assert else_branch["required"] == ["x", "y", "width", "height"]
    for key in ("x", "y", "width", "height"):
        assert else_branch["properties"][key] == {"not": {"type": "null"}}
    assert else_branch["properties"]["from"] == {"type": "null"}
    assert else_branch["properties"]["to"] == {"type": "null"}


def test_set_theme_schema_expresses_nonempty_requirement() -> None:
    schema = SetThemeOperation.model_json_schema()
    assert schema["anyOf"] == [
        {"required": ["colors"], "properties": {"colors": {"type": "object", "minProperties": 1}}},
        {"required": ["fonts"], "properties": {"fonts": {"type": "object", "minProperties": 1}}},
    ]


# add_table.fills / col_widths ------------------------------------------------

def test_add_table_accepts_fills_matrix_matching_rows() -> None:
    _validates(AddTableOperation, {
        "op": "add_table", "slide": 0, "at": [0, 0], "size": [9, 3],
        "rows": [["A", "B"], ["1", "2"]],
        "fills": [["112233", "none"], [None, "445566"]],
        "col_widths": [4.5, 4.5],
    })


def test_add_table_rejects_short_fill_row() -> None:
    _rejects(AddTableOperation, {
        "op": "add_table", "slide": 0, "at": [0, 0], "size": [9, 3],
        "rows": [["A", "B"], ["1", "2"]],
        "fills": [["112233"], ["none", "none"]],
    })


def test_add_table_rejects_wrong_fill_row_count() -> None:
    _rejects(AddTableOperation, {
        "op": "add_table", "slide": 0, "at": [0, 0], "size": [9, 3],
        "rows": [["A", "B"], ["1", "2"]],
        "fills": [["112233", "none"]],
    })


def test_add_table_rejects_col_widths_count_mismatch() -> None:
    _rejects(AddTableOperation, {
        "op": "add_table", "slide": 0, "at": [0, 0], "size": [9, 3],
        "rows": [["A", "B"], ["1", "2"]],
        "col_widths": [4.5],
    })


# swap_image target modes ------------------------------------------------------

def test_swap_image_accepts_object_media_and_rid_with_slide() -> None:
    _validates(SwapImageOperation, {"op": "swap_image", "object": "s0:s4", "image": "x.png"})
    _validates(SwapImageOperation, {"op": "swap_image", "media": "image1.png", "image": "x.png"})
    _validates(SwapImageOperation, {"op": "swap_image", "rid": "rId3", "slide": 0, "image": "x.png"})


def test_swap_image_rejects_rid_without_slide() -> None:
    _rejects(SwapImageOperation, {"op": "swap_image", "rid": "rId3", "image": "x.png"})


def test_swap_image_rejects_multiple_targets() -> None:
    _rejects(SwapImageOperation, {"op": "swap_image", "object": "s0:s4", "rid": "rId3", "slide": 0, "image": "x.png"})
    _rejects(SwapImageOperation, {"op": "swap_image", "media": "image1.png", "object": "s0:s4", "image": "x.png"})


# add_shape line text ----------------------------------------------------------

def test_add_shape_line_rejects_text() -> None:
    _rejects(AddShapeOperation, {
        "op": "add_shape", "slide": 0, "kind": "line",
        "from": [0, 0], "to": [5, 5], "text": "no text on lines",
    })


def test_add_shape_line_rejects_absolute_geometry() -> None:
    _rejects(AddShapeOperation, {
        "op": "add_shape", "slide": 0, "kind": "line",
        "from": [0, 0], "to": [5, 5], "x": 1.0, "y": 1.0,
    })


def test_add_shape_non_line_rejects_from_to() -> None:
    _rejects(AddShapeOperation, {
        "op": "add_shape", "slide": 0, "kind": "textbox",
        "x": 1, "y": 2, "width": 4, "height": 1.5, "from": [0, 0], "to": [5, 5],
    })


def test_add_shape_line_without_text_is_valid() -> None:
    _validates(AddShapeOperation, {
        "op": "add_shape", "slide": 0, "kind": "line", "from": [0, 0], "to": [5, 5],
    })


# rich paragraph text/runs -----------------------------------------------------

def test_paragraph_accepts_text_or_nonempty_runs_exclusively() -> None:
    _validates(ParagraphSpec, {"text": "one"})
    _validates(ParagraphSpec, {"runs": [{"text": "a"}, {"text": "b", "bold": True}]})


def test_paragraph_rejects_both_text_and_runs() -> None:
    _rejects(ParagraphSpec, {"text": "one", "runs": [{"text": "a"}]})


def test_paragraph_rejects_neither_text_nor_runs() -> None:
    _rejects(ParagraphSpec, {"bullet": False})


def test_paragraph_rejects_empty_runs() -> None:
    _rejects(ParagraphSpec, {"runs": []})


# transition option matrix -----------------------------------------------------

def test_transition_accepts_type_compatible_options() -> None:
    _validates(TransitionSpec, {"type": "fade"})
    _validates(TransitionSpec, {"type": "push", "dir": "l"})
    _validates(TransitionSpec, {"type": "split", "orient": "horz", "dir": "in"})
    _validates(TransitionSpec, {"type": "cover", "dir": "ru"})
    _validates(TransitionSpec, {"type": "zoom", "dir": "out", "speed": "fast"})


@pytest.mark.parametrize("payload", [
    {"type": "fade", "dir": "l"},
    {"type": "fade", "orient": "horz"},
    {"type": "push", "orient": "horz"},
    {"type": "push", "dir": "in"},
    {"type": "split", "dir": "l"},
    {"type": "cover", "dir": "in"},
    {"type": "zoom", "orient": "horz"},
])
def test_transition_rejects_type_incompatible_options(payload: dict) -> None:
    _rejects(TransitionSpec, payload)


# set_theme non-empty ----------------------------------------------------------

def test_set_theme_rejects_empty_colors_and_empty_fonts() -> None:
    _rejects(SetThemeOperation, {"op": "set_theme", "colors": {}})
    _rejects(SetThemeOperation, {"op": "set_theme", "fonts": {}})
    _rejects(SetThemeOperation, {"op": "set_theme", "colors": {}, "fonts": {}})


def test_set_theme_accepts_at_least_one_value() -> None:
    _validates(SetThemeOperation, {"op": "set_theme", "colors": {"accent1": "BB7B19"}})
    _validates(SetThemeOperation, {"op": "set_theme", "fonts": {"major": "Georgia"}})
    _validates(SetThemeOperation, {"op": "set_theme", "colors": {"accent1": "BB7B19"}, "fonts": {}})

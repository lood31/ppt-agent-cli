from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, Callable, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, model_validator


SCHEMA_VERSION = "2.1"
ObjectId = Annotated[str, Field(pattern=r"^s\d+:(?:s|o)\d+$", description="精确对象 ID；先用 inspect 获取，页码从 0 开始")]
Point: TypeAlias = tuple[float, float]
Size: TypeAlias = tuple[Annotated[float, Field(gt=0)], Annotated[float, Field(gt=0)]]
HexColor = Annotated[str, Field(pattern=r"^#?[0-9A-Fa-f]{6}$", description="6 位 RGB 十六进制颜色")]


@dataclass(frozen=True)
class OperationSpec:
    """统一 operation 注册表条目。

    model/example/errors 驱动能力发现；backend 决定引擎/WPS 路由；
    reducer 计算批次最终 Postcondition（当前只有 transition）。
    """

    name: str
    model: type[StrictModel]
    backend: Literal["engine", "wps"]
    use_when: str
    example: dict[str, Any]
    errors: list[str]
    reducer: Callable[[dict[int, Any], dict[str, Any]], None] | None = None


# Postcondition reducers（Planner 使用，替代散落在 service 中的特判） ---------


def _reduce_set_slide(state: dict[int, Any], operation: dict[str, Any]) -> None:
    if "transition" not in operation:
        return
    if isinstance(operation["transition"], dict):
        state[operation["slide"]] = operation["transition"]
    else:  # "none"：引擎已删除切换，无需恢复
        state.pop(operation["slide"], None)


def _reduce_set_transition(state: dict[int, Any], operation: dict[str, Any]) -> None:
    state.pop(operation["slide"], None)


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        json_schema_extra={"additionalProperties": False},
    )


class RunSpec(StrictModel):
    text: str
    font_size: float | None = Field(default=None, gt=0, description="磅")
    font_name: str | None = None
    bold: bool | None = None
    italic: bool | None = None
    underline: bool | None = None
    color: HexColor | None = None
    link: str | None = None


class ParagraphSpec(StrictModel):
    model_config = ConfigDict(
        json_schema_extra={
            "oneOf": [
                {"required": ["text"], "properties": {"text": {"type": "string"}, "runs": {"type": "null"}}},
                {"required": ["runs"], "properties": {"runs": {"type": "array", "minItems": 1}, "text": {"type": "null"}}},
            ],
        },
    )
    text: str | None = None
    runs: list[RunSpec] | None = Field(default=None, min_length=1)
    bullet: bool | Literal["number"] | None = None
    level: int | None = Field(default=None, ge=0, le=8)
    alignment: Literal["LEFT", "CENTER", "RIGHT", "JUSTIFY"] | None = None
    font_size: float | None = Field(default=None, gt=0, description="磅")
    font_name: str | None = None
    bold: bool | None = None
    italic: bool | None = None
    underline: bool | None = None
    color: HexColor | None = None

    @model_validator(mode="after")
    def require_text_or_runs(self) -> "ParagraphSpec":
        if (self.text is None) == (self.runs is None):
            raise ValueError("段落必须且只能提供 text 或 runs 之一")
        if self.runs is not None and not self.runs:
            raise ValueError("runs 不能为空数组")
        return self


TextContent: TypeAlias = str | list[str | ParagraphSpec]


class ObjectOperation(StrictModel):
    object: ObjectId
    expect_count: int | None = Field(default=None, ge=0, description="保留兼容；精确对象 ID 通常无需填写")


class SetTextOperation(ObjectOperation):
    op: Literal["set_text"]
    text: TextContent
    cell: tuple[Annotated[int, Field(ge=0)], Annotated[int, Field(ge=0)]] | None = None
    anchor: Literal["TOP", "MIDDLE", "BOTTOM"] | None = None


class ReplaceTextOperation(StrictModel):
    model_config = ConfigDict(
        json_schema_extra={
            "allOf": [{
                "if": {"properties": {"scope": {"const": "slide"}}, "required": ["scope"]},
                "then": {"required": ["slide"], "properties": {"slide": {"not": {"type": "null"}}}},
            }],
        },
    )
    op: Literal["replace_text"]
    from_text: str = Field(alias="from", min_length=1)
    to: str
    scope: Literal["deck", "slide", "master"] = "deck"
    slide: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def require_slide_scope(self) -> "ReplaceTextOperation":
        if self.scope == "slide" and self.slide is None:
            raise ValueError("scope=slide 时必须提供 slide")
        return self


class ReplaceColorOperation(StrictModel):
    model_config = ConfigDict(
        json_schema_extra={
            "allOf": [{
                "if": {"properties": {"scope": {"const": "slide"}}, "required": ["scope"]},
                "then": {"required": ["slide"], "properties": {"slide": {"not": {"type": "null"}}}},
            }],
        },
    )
    op: Literal["replace_color"]
    from_color: HexColor = Field(alias="from")
    to: HexColor
    scope: Literal["deck", "slide", "master"] = "deck"
    slide: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def require_slide_scope(self) -> "ReplaceColorOperation":
        if self.scope == "slide" and self.slide is None:
            raise ValueError("scope=slide 时必须提供 slide")
        return self


class SwapImageOperation(StrictModel):
    model_config = ConfigDict(
        json_schema_extra={
            "oneOf": [
                {
                    "required": ["object"],
                    "properties": {
                        "object": {"type": "string", "pattern": r"^s\d+:(?:s|o)\d+$"},
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
            ],
        },
    )
    op: Literal["swap_image"]
    image: str = Field(min_length=1, description="本地图片路径")
    object: ObjectId | None = None
    media: str | None = None
    rid: str | None = None
    slide: int | None = Field(default=None, ge=0, description="按 rid 定位时的目标页，0-based")

    @model_validator(mode="after")
    def require_target(self) -> "SwapImageOperation":
        targets = [value is not None for value in (self.object, self.media, self.rid)]
        if sum(targets) != 1:
            raise ValueError("必须且只能提供 object、media 或 rid 之一")
        if self.rid is not None and self.slide is None:
            raise ValueError("按 rid 定位必须同时提供 slide")
        return self


class SetNotesOperation(StrictModel):
    op: Literal["set_notes"]
    slide: int = Field(ge=0)
    notes: str


class SetPropsOperation(StrictModel):
    model_config = ConfigDict(
        json_schema_extra={
            "anyOf": [
                {"required": [field], "properties": {field: {"not": {"type": "null"}}}}
                for field in ("title", "subject", "author", "keywords", "comments", "category", "last_modified_by")
            ],
        },
    )
    op: Literal["set_props"]
    title: str | None = None
    subject: str | None = None
    author: str | None = None
    keywords: str | None = None
    comments: str | None = None
    category: str | None = None
    last_modified_by: str | None = None

    @model_validator(mode="after")
    def require_property(self) -> "SetPropsOperation":
        if not any(value is not None for key, value in self.__dict__.items() if key != "op"):
            raise ValueError("至少提供一个文档属性")
        return self


class GradientSpec(StrictModel):
    colors: list[HexColor] = Field(min_length=2, max_length=2)
    angle: float | None = Field(default=None, ge=0, le=360, description="角度")
    positions: tuple[Annotated[float, Field(ge=0, le=1)], Annotated[float, Field(ge=0, le=1)]] | None = None


class ImageBackground(StrictModel):
    image: str


class GradientBackground(StrictModel):
    gradient: GradientSpec


# 与固定引擎 deck.py 的 TRANSITION_TYPES 保持一致
TRANSITION_OPTIONS: dict[str, dict[str, tuple[str, ...]]] = {
    "fade": {},
    "cut": {},
    "dissolve": {},
    "push": {"dir": ("l", "r", "u", "d")},
    "wipe": {"dir": ("l", "r", "u", "d")},
    "split": {"orient": ("horz", "vert"), "dir": ("in", "out")},
    "cover": {"dir": ("l", "r", "u", "d", "ld", "lu", "rd", "ru")},
    "uncover": {"dir": ("l", "r", "u", "d", "ld", "lu", "rd", "ru")},
    "zoom": {"dir": ("in", "out")},
}

# 与固定引擎 deck.py 的 TRANSITION_TYPES 保持一致。
# null 与省略等价：被禁用的键只允许 null/缺省；允许的键接受 null 或枚举值。
_TRANSITION_SCHEMA_RULES: list[dict[str, Any]] = [
    {
        "if": {"properties": {"type": {"const": type_name}}, "required": ["type"]},
        "then": {
            "allOf": [
                *[
                    {"properties": {key: {"type": "null"}}}
                    for key in ("dir", "orient")
                    if key not in options
                ],
                *[
                    {"properties": {key: {"anyOf": [{"type": "null"}, {"enum": list(values)}]}}}
                    for key, values in options.items()
                ],
            ],
        },
    }
    for type_name, options in TRANSITION_OPTIONS.items()
]


class TransitionSpec(StrictModel):
    model_config = ConfigDict(json_schema_extra={"allOf": _TRANSITION_SCHEMA_RULES})
    type: Literal["fade", "cut", "dissolve", "push", "wipe", "split", "cover", "uncover", "zoom"]
    speed: Literal["slow", "med", "fast"] | None = None
    dir: Literal["l", "r", "u", "d", "ld", "lu", "rd", "ru", "in", "out"] | None = None
    orient: Literal["horz", "vert"] | None = None
    advance_on_click: bool | None = None
    advance_after: float | None = Field(default=None, ge=0, description="秒")

    @model_validator(mode="after")
    def require_type_compatible_options(self) -> "TransitionSpec":
        allowed = TRANSITION_OPTIONS[self.type]
        for key in ("dir", "orient"):
            value = getattr(self, key)
            if value is None:
                continue
            if key not in allowed:
                raise ValueError(f"{self.type} 切换不接受 {key} 选项")
            if value not in allowed[key]:
                raise ValueError(f"{self.type} 切换的 {key} 只允许：{'/'.join(allowed[key])}")
        return self


class SetSlideOperation(StrictModel):
    model_config = ConfigDict(
        json_schema_extra={
            "anyOf": [
                {"required": ["hidden"], "properties": {"hidden": {"not": {"type": "null"}}}},
                {"required": ["background"], "properties": {"background": {"not": {"type": "null"}}}},
                {"required": ["transition"], "properties": {"transition": {"not": {"type": "null"}}}},
            ],
        },
    )
    op: Literal["set_slide"]
    slide: int = Field(ge=0)
    hidden: bool | None = None
    background: HexColor | ImageBackground | GradientBackground | None = None
    transition: TransitionSpec | Literal["none"] | None = None

    @model_validator(mode="after")
    def require_change(self) -> "SetSlideOperation":
        if self.hidden is None and self.background is None and self.transition is None:
            raise ValueError("至少提供 hidden、background 或 transition 之一")
        return self


class ThemeColors(StrictModel):
    dk1: HexColor | None = None
    lt1: HexColor | None = None
    dk2: HexColor | None = None
    lt2: HexColor | None = None
    accent1: HexColor | None = None
    accent2: HexColor | None = None
    accent3: HexColor | None = None
    accent4: HexColor | None = None
    accent5: HexColor | None = None
    accent6: HexColor | None = None
    hlink: HexColor | None = None
    folHlink: HexColor | None = None


class ThemeFonts(StrictModel):
    major: str | None = None
    minor: str | None = None


class SetThemeOperation(StrictModel):
    model_config = ConfigDict(
        json_schema_extra={
            "anyOf": [
                {"required": ["colors"], "properties": {"colors": {"type": "object", "minProperties": 1}}},
                {"required": ["fonts"], "properties": {"fonts": {"type": "object", "minProperties": 1}}},
            ],
        },
    )
    op: Literal["set_theme"]
    colors: ThemeColors | None = None
    fonts: ThemeFonts | None = None
    master: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def require_theme_change(self) -> "SetThemeOperation":
        provided_colors = self.colors.model_dump(exclude_none=True) if self.colors is not None else {}
        provided_fonts = self.fonts.model_dump(exclude_none=True) if self.fonts is not None else {}
        if not provided_colors and not provided_fonts:
            raise ValueError("至少提供一种主题颜色或字体")
        return self


class MoveOperation(ObjectOperation):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        json_schema_extra={
            "oneOf": [
                {
                    "required": ["x", "y"],
                    "properties": {"x": {"not": {"type": "null"}}, "y": {"not": {"type": "null"}}},
                },
                {
                    "required": ["dx", "dy"],
                    "properties": {"dx": {"not": {"type": "null"}}, "dy": {"not": {"type": "null"}}},
                },
            ],
        },
    )
    op: Literal["move"]
    x: float | None = Field(default=None, description="绝对横坐标，英寸")
    y: float | None = Field(default=None, description="绝对纵坐标，英寸")
    dx: float | None = Field(default=None, description="水平偏移，英寸")
    dy: float | None = Field(default=None, description="垂直偏移，英寸")

    @model_validator(mode="after")
    def one_coordinate_mode(self) -> "MoveOperation":
        absolute = self.x is not None or self.y is not None
        relative = self.dx is not None or self.dy is not None
        if absolute == relative or (absolute and (self.x is None or self.y is None)) or (relative and (self.dx is None or self.dy is None)):
            raise ValueError("必须且只能完整提供 x/y 或 dx/dy；单位为英寸")
        return self


class ResizeOperation(ObjectOperation):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        json_schema_extra={
            "oneOf": [
                {
                    "required": ["width", "height"],
                    "properties": {"width": {"not": {"type": "null"}}, "height": {"not": {"type": "null"}}},
                },
                {
                    "required": ["scale"],
                    "properties": {"scale": {"not": {"type": "null"}}},
                },
            ],
        },
    )
    op: Literal["resize"]
    width: float | None = Field(default=None, gt=0, description="宽，英寸")
    height: float | None = Field(default=None, gt=0, description="高，英寸")
    scale: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def one_size_mode(self) -> "ResizeOperation":
        explicit = self.width is not None or self.height is not None
        if explicit == (self.scale is not None) or (explicit and (self.width is None or self.height is None)):
            raise ValueError("必须且只能完整提供 width/height（英寸）或 scale")
        return self


class StyleFields(StrictModel):
    font_size: float | None = Field(default=None, gt=0, description="磅")
    font_name: str | None = None
    bold: bool | None = None
    italic: bool | None = None
    underline: bool | None = None
    color: HexColor | None = None
    fill: HexColor | Literal["none"] | None = None
    gradient: GradientSpec | None = None
    line: Literal["none"] | None = None
    line_color: HexColor | None = None
    line_width: float | None = Field(default=None, ge=0, description="磅")
    line_dash: Literal["solid", "dash", "dot", "dash_dot", "dash_dot_dot", "long_dash", "long_dash_dot", "round_dot", "square_dot"] | None = None
    rotation: float | None = Field(default=None, ge=0, le=360, description="顺时针角度")
    insets: tuple[float, float, float, float] | None = Field(default=None, description="左上右下内边距，英寸")
    anchor: Literal["TOP", "MIDDLE", "BOTTOM"] | None = None
    adjustments: list[Annotated[float, Field(ge=0, le=1)]] | None = None
    shadow: bool | None = None
    alt_text: str | None = None


STYLE_FIELD_NAMES = set(StyleFields.model_fields)


class SetStyleOperation(ObjectOperation, StyleFields):
    model_config = ConfigDict(
        json_schema_extra={
            "anyOf": [
                {"required": [field], "properties": {field: {"not": {"type": "null"}}}}
                for field in sorted(STYLE_FIELD_NAMES)
            ],
        },
    )
    op: Literal["set_style"]

    @model_validator(mode="after")
    def require_style(self) -> "SetStyleOperation":
        if not any(getattr(self, name) is not None for name in STYLE_FIELD_NAMES):
            raise ValueError("至少提供一个样式字段")
        return self


class DeleteOperation(ObjectOperation):
    op: Literal["delete"]


class DuplicateOperation(ObjectOperation):
    op: Literal["duplicate"]
    offset: Point | None = Field(default=None, description="偏移 [dx,dy]，英寸")
    at: Point | None = Field(default=None, description="绝对位置 [x,y]，英寸")
    text: TextContent | None = None


class CopyShapeOperation(StrictModel):
    op: Literal["copy_shape"]
    from_slide: int = Field(ge=0)
    shape: Annotated[str, Field(pattern=r"^(?:s|o)\d+$")]
    slide: int = Field(ge=0, description="目标页，0-based")
    at: Point | None = Field(default=None, description="目标位置，英寸")
    text: TextContent | None = None


class AddShapeOperation(StyleFields):
    model_config = ConfigDict(
        json_schema_extra={
            "allOf": [{
                "if": {"properties": {"kind": {"const": "line"}}, "required": ["kind"]},
                "then": {
                    "required": ["from", "to"],
                    "properties": {
                        "from": {"not": {"type": "null"}},
                        "to": {"not": {"type": "null"}},
                        "text": {"type": "null"},
                        "x": {"type": "null"},
                        "y": {"type": "null"},
                        "width": {"type": "null"},
                        "height": {"type": "null"},
                    },
                },
                "else": {
                    "required": ["x", "y", "width", "height"],
                    "properties": {
                        "x": {"not": {"type": "null"}},
                        "y": {"not": {"type": "null"}},
                        "width": {"not": {"type": "null"}},
                        "height": {"not": {"type": "null"}},
                        "from": {"type": "null"},
                        "to": {"type": "null"},
                    },
                },
            }],
        },
    )
    op: Literal["add_shape"]
    slide: int = Field(ge=0)
    kind: str = "textbox"
    x: float | None = Field(default=None, description="左坐标，英寸")
    y: float | None = Field(default=None, description="上坐标，英寸")
    width: float | None = Field(default=None, gt=0, description="宽，英寸")
    height: float | None = Field(default=None, gt=0, description="高，英寸")
    from_point: Point | None = Field(default=None, alias="from", description="线起点，英寸")
    to: Point | None = Field(default=None, description="线终点，英寸")
    text: TextContent | None = None
    name: str | None = None

    @model_validator(mode="after")
    def require_geometry(self) -> "AddShapeOperation":
        if self.kind == "line":
            if self.from_point is None or self.to is None:
                raise ValueError("kind=line 时必须提供 from/to")
            if self.text is not None:
                raise ValueError("kind=line 不能携带 text")
            if any(value is not None for value in (self.x, self.y, self.width, self.height)):
                raise ValueError("kind=line 不接受 x/y/width/height，请使用 from/to")
        else:
            if any(value is None for value in (self.x, self.y, self.width, self.height)):
                raise ValueError("非 line 形状必须提供 x/y/width/height，单位为英寸")
            if self.from_point is not None or self.to is not None:
                raise ValueError("非 line 形状不接受 from/to，请使用 x/y/width/height")
        return self


class AddPictureOperation(StrictModel):
    model_config = ConfigDict(
        json_schema_extra={
            "not": {
                "anyOf": [
                    {
                        "required": ["width", "height"],
                        "properties": {"width": {"not": {"type": "null"}}, "height": {"not": {"type": "null"}}},
                    },
                    {
                        "required": ["width", "size"],
                        "properties": {"width": {"not": {"type": "null"}}, "size": {"not": {"type": "null"}}},
                    },
                    {
                        "required": ["height", "size"],
                        "properties": {"height": {"not": {"type": "null"}}, "size": {"not": {"type": "null"}}},
                    },
                ],
            },
        },
    )
    op: Literal["add_picture"]
    slide: int = Field(ge=0)
    image: str
    at: Point = Field(description="左上角 [x,y]，英寸")
    width: float | None = Field(default=None, gt=0, description="英寸，保持宽高比")
    height: float | None = Field(default=None, gt=0, description="英寸，保持宽高比")
    size: Size | None = Field(default=None, description="强制 [宽,高]，英寸")
    crop: tuple[Annotated[float, Field(ge=0, le=1)], Annotated[float, Field(ge=0, le=1)], Annotated[float, Field(ge=0, le=1)], Annotated[float, Field(ge=0, le=1)]] | None = None
    shadow: bool | None = None
    alt_text: str | None = None

    @model_validator(mode="after")
    def one_size_mode(self) -> "AddPictureOperation":
        if sum(value is not None for value in (self.width, self.height, self.size)) > 1:
            raise ValueError("width、height、size 最多提供一种")
        return self


class AddTableOperation(StrictModel):
    op: Literal["add_table"]
    slide: int = Field(ge=0)
    at: Point = Field(description="左上角，英寸")
    size: Size = Field(description="宽高，英寸")
    rows: list[list[str | int | float]] = Field(min_length=1)
    name: str | None = None
    font_size: float | None = Field(default=None, gt=0, description="磅")
    color: HexColor | None = None
    fill: HexColor | Literal["none"] | None = None
    fills: list[list[HexColor | Literal["none"] | None]] | None = None
    col_widths: list[Annotated[float, Field(gt=0)]] | None = Field(default=None, description="各列宽，英寸")
    first_row: bool | None = None
    banding: bool | None = None

    @model_validator(mode="after")
    def rectangular_rows(self) -> "AddTableOperation":
        widths = {len(row) for row in self.rows}
        if widths == {0} or len(widths) != 1:
            raise ValueError("rows 必须是非空矩形二维数组")
        if self.fills is not None and (
            len(self.fills) != len(self.rows)
            or any(len(fill_row) != len(self.rows[index]) for index, fill_row in enumerate(self.fills))
        ):
            raise ValueError("fills 必须是逐格矩阵：行数与列数都要和 rows 一致")
        if self.col_widths is not None and len(self.col_widths) != len(self.rows[0]):
            raise ValueError("col_widths 数量必须等于列数")
        return self


class AddSlideOperation(StrictModel):
    op: Literal["add_slide"]
    layout: str | int | None = None
    at: int | None = Field(default=None, ge=0, description="插入位置，0-based；省略则追加")


class ReorderOperation(ObjectOperation):
    op: Literal["reorder"]
    z: Literal["front", "back", "forward", "backward"]


class AddRowOperation(ObjectOperation):
    op: Literal["add_row"]
    cells: list[str | int | float]
    copy_index: int | None = Field(default=None, alias="copy")
    at: int | None = Field(default=None, ge=0)


class DeleteRowOperation(ObjectOperation):
    op: Literal["delete_row"]
    row: int


class AddColOperation(ObjectOperation):
    op: Literal["add_col"]
    cells: list[str | int | float]
    copy_index: int | None = Field(default=None, alias="copy")
    at: int | None = Field(default=None, ge=0)


class DeleteColOperation(ObjectOperation):
    op: Literal["delete_col"]
    col: int


class AddAnimationOperation(ObjectOperation):
    op: Literal["add_animation"]
    effect: Literal["appear", "fade", "fly_in"] = "fade"
    trigger: Literal["on_click", "with_previous", "after_previous"] = "on_click"
    paragraphs: Literal["all"] | None = Field(
        default=None,
        description="按段落整体展开；CLI 只调用一次 WPS AddEffect，省略表示整个对象",
    )
    duration: float | None = Field(default=None, ge=0, description="秒")
    delay: float | None = Field(default=None, ge=0, description="秒")


class SetTransitionOperation(StrictModel):
    op: Literal["set_transition"]
    slide: int = Field(ge=0)
    transition: Literal["none", "fade", "push", "wipe"] = "fade"


class SetChartTitleOperation(ObjectOperation):
    op: Literal["set_chart_title"]
    title: str


Operation = Annotated[
    SetTextOperation | ReplaceTextOperation | ReplaceColorOperation | SwapImageOperation |
    SetNotesOperation | SetPropsOperation | SetSlideOperation | SetThemeOperation |
    MoveOperation | ResizeOperation | SetStyleOperation | DeleteOperation | DuplicateOperation |
    CopyShapeOperation | AddShapeOperation | AddPictureOperation | AddTableOperation |
    AddSlideOperation | ReorderOperation | AddRowOperation | DeleteRowOperation |
    AddColOperation | DeleteColOperation | AddAnimationOperation | SetTransitionOperation |
    SetChartTitleOperation,
    Field(discriminator="op"),
]


OPERATION_SPECS: list[OperationSpec] = [
    OperationSpec("set_text", SetTextOperation, "engine", "修改一个对象或表格单元格的文字",
                  {"op": "set_text", "object": "s0:s2", "text": "新标题"},
                  ["object 必须来自 inspect", "表格单元格需提供 cell", "段落只能提供 text 或 runs 之一，runs 不能为空"]),
    OperationSpec("replace_text", ReplaceTextOperation, "engine", "在整份文档或指定页批量替换文字",
                  {"op": "replace_text", "from": "旧文本", "to": "新文本", "scope": "deck"},
                  ["跨 run 文本不能直接替换，改用 set_text"]),
    OperationSpec("replace_color", ReplaceColorOperation, "engine", "批量替换硬编码颜色",
                  {"op": "replace_color", "from": "112233", "to": "445566", "scope": "deck"},
                  ["只接受 6 位 RGB；主题色请用 set_theme"]),
    OperationSpec("swap_image", SwapImageOperation, "engine", "替换现有图片并保留图片框",
                  {"op": "swap_image", "object": "s0:s4", "image": "D:/assets/new.png"},
                  ["图片必须是本地可读文件", "对象必须是图片", "object/media/rid 只能选一种；按 rid 定位必须同时提供 slide"]),
    OperationSpec("set_notes", SetNotesOperation, "engine", "设置单页讲者备注",
                  {"op": "set_notes", "slide": 0, "notes": "讲者备注"},
                  ["slide 从 0 开始"]),
    OperationSpec("set_props", SetPropsOperation, "engine", "修改文档标题、作者等属性",
                  {"op": "set_props", "title": "项目汇报", "author": "团队"},
                  ["至少提供一个属性"]),
    OperationSpec("set_slide", SetSlideOperation, "engine", "修改单页背景、隐藏状态或基础切换",
                  {"op": "set_slide", "slide": 0, "background": "FFFFFF"},
                  ["至少提供 hidden、background 或 transition", "dir/orient 只对相应切换类型有效"],
                  _reduce_set_slide),
    OperationSpec("set_theme", SetThemeOperation, "engine", "修改主题颜色或字体",
                  {"op": "set_theme", "colors": {"accent1": "BB7B19"}, "fonts": {"major": "Georgia"}},
                  ["主题色与硬编码颜色不同", "至少提供一种非空主题颜色或字体"]),
    OperationSpec("move", MoveOperation, "engine", "移动现有对象",
                  {"op": "move", "object": "s0:s2", "x": 1.05, "y": 0.6},
                  ["x/y 与 dx/dy 只能选一组", "单位是英寸"]),
    OperationSpec("resize", ResizeOperation, "engine", "调整现有对象尺寸",
                  {"op": "resize", "object": "s0:s2", "width": 4.0, "height": 1.5},
                  ["width/height 与 scale 只能选一种", "单位是英寸"]),
    OperationSpec("set_style", SetStyleOperation, "engine", "修改文字、填充、线条等样式",
                  {"op": "set_style", "object": "s0:s2", "font_size": 32},
                  ["font_size 单位为磅", "至少提供一个样式字段"]),
    OperationSpec("delete", DeleteOperation, "engine", "删除现有对象",
                  {"op": "delete", "object": "s0:s2"},
                  ["删除组会同时删除组内对象"]),
    OperationSpec("duplicate", DuplicateOperation, "engine", "在同一页复制对象",
                  {"op": "duplicate", "object": "s0:s2", "offset": [0, 1.2]},
                  ["offset 单位为英寸"]),
    OperationSpec("copy_shape", CopyShapeOperation, "engine", "跨页面复制对象",
                  {"op": "copy_shape", "from_slide": 1, "shape": "s12", "slide": 0, "at": [1, 2]},
                  ["shape 是源页内 ID，不含页前缀"]),
    OperationSpec("add_shape", AddShapeOperation, "engine", "添加文本框、基础形状或线条",
                  {"op": "add_shape", "slide": 0, "kind": "textbox", "x": 1, "y": 2, "width": 4, "height": 1.5, "text": "标签"},
                  ["非线条必须提供完整几何；单位为英寸", "kind=line 使用 from/to，不接受 x/y/width/height 与 text；非 line 不接受 from/to"]),
    OperationSpec("add_picture", AddPictureOperation, "engine", "添加本地图片",
                  {"op": "add_picture", "slide": 0, "image": "D:/assets/a.png", "at": [1, 2], "width": 4},
                  ["width、height、size 最多选一种"]),
    OperationSpec("add_table", AddTableOperation, "engine", "添加基础表格",
                  {"op": "add_table", "slide": 0, "at": [0.5, 1.5], "size": [9, 3], "rows": [["A", "B"], ["1", "2"]]},
                  ["rows 必须是矩形二维数组", "fills 必须与 rows 逐格同形；col_widths 数量等于列数"]),
    OperationSpec("add_slide", AddSlideOperation, "engine", "添加幻灯片",
                  {"op": "add_slide", "layout": "Blank", "at": 2},
                  ["layout 名称必须唯一匹配"]),
    OperationSpec("reorder", ReorderOperation, "engine", "调整对象层级",
                  {"op": "reorder", "object": "s0:s2", "z": "front"},
                  ["z 仅支持 front/back/forward/backward"]),
    OperationSpec("add_row", AddRowOperation, "engine", "向现有表格添加行",
                  {"op": "add_row", "object": "s0:s8", "cells": ["A", "B"], "at": 1},
                  ["不支持合并单元格表格"]),
    OperationSpec("delete_row", DeleteRowOperation, "engine", "删除现有表格行",
                  {"op": "delete_row", "object": "s0:s8", "row": 1},
                  ["不支持合并单元格表格"]),
    OperationSpec("add_col", AddColOperation, "engine", "向现有表格添加列",
                  {"op": "add_col", "object": "s0:s8", "cells": ["A", "1"], "at": 1},
                  ["cells 数量应与行数一致"]),
    OperationSpec("delete_col", DeleteColOperation, "engine", "删除现有表格列",
                  {"op": "delete_col", "object": "s0:s8", "col": 1},
                  ["不支持合并单元格表格"]),
    OperationSpec("add_animation", AddAnimationOperation, "wps", "添加基础对象或逐段动画",
                  {"op": "add_animation", "object": "s0:s5", "effect": "appear", "trigger": "with_previous", "paragraphs": "all"},
                  ["paragraphs 只接受 all；省略表示整个对象", "同一对象不能同时提交整体与逐段进入动画"]),
    OperationSpec("set_transition", SetTransitionOperation, "wps", "设置幻灯片切换",
                  {"op": "set_transition", "slide": 0, "transition": "fade"},
                  ["slide 从 0 开始"],
                  _reduce_set_transition),
    OperationSpec("set_chart_title", SetChartTitleOperation, "wps", "修改原生图表标题",
                  {"op": "set_chart_title", "object": "s1:s4", "title": "月度趋势"},
                  ["对象必须是原生图表"]),
]

OPERATIONS: dict[str, OperationSpec] = {spec.name: spec for spec in OPERATION_SPECS}
OPERATION_MODELS = {spec.name: spec.model for spec in OPERATION_SPECS}
OPERATION_GUIDE = {
    spec.name: {"example": spec.example, "errors": spec.errors, "wps": spec.backend == "wps"}
    for spec in OPERATION_SPECS
}
OPERATION_USE_WHEN = {spec.name: spec.use_when for spec in OPERATION_SPECS}


class PatchRequest(StrictModel):
    request_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="幂等请求 ID；省略时 CLI 根据 document_id、revision 和 operations 安全生成",
    )
    document_id: str
    revision: str
    operations: list[Operation] = Field(min_length=1, max_length=200)


class SlideSpec(StrictModel):
    layout: Literal[
        "title", "title_content", "section", "two_column", "comparison",
        "stat", "timeline", "quote", "image_text", "blank",
    ] = "title_content"
    title: str = ""
    body: list[str] = Field(default_factory=list)
    notes: str | None = None


class CreateSpec(StrictModel):
    title: str | None = None
    slides: list[SlideSpec] = Field(min_length=1, max_length=100)
    width: float = Field(default=13.333, gt=0)
    height: float = Field(default=7.5, gt=0)


class ResultEnvelope(StrictModel):
    schema_version: str = SCHEMA_VERSION
    ok: bool
    command: str
    document_id: str | None = None
    revision: str | None = None
    engine_version: str = "hands-on-deck@a24b996"
    wps_version: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)

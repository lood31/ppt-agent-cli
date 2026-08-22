# ppt-agent-cli

> [!WARNING]
> **当前状态：半成品 / MVP 预览版（v0.2.4b1）**。核心闭环和主要安全校验已实现，但项目仍在持续开发与验证中；WPS/Windows 环境差异、复杂 PPT 特性和部分边界场景可能仍有缺陷。请勿将当前版本用于生产数据或唯一副本，使用前务必保留原始 PPTX 并先在副本上验证。

面向 AI Agent 的 WPS-first PPTX 命令行适配层。`stdout` 只输出版本化 JSON；PPTX 普通编辑由固定版本的 `hands-on-deck` 执行，WPS COM 是发布前的最后写入者与验证者。

已构建的 Windows 单文件版本位于 `dist/ppt-agent.exe`，无需 Python 即可运行。

## 安装与卸载

发布包解压后，可按当前 Windows 用户安装；默认安装到 `%LOCALAPPDATA%\Programs\ppt-agent` 并加入用户 PATH：

```powershell
powershell -ExecutionPolicy Bypass -File tools\install.ps1
ppt-agent --version
ppt-agent --pretty doctor
```

若不希望修改用户 PATH：

```powershell
powershell -ExecutionPolicy Bypass -File tools\install.ps1 -NoPath
```

卸载默认保留 `%LOCALAPPDATA%\ppt-agent` 中的 baseline、review、request 与事务状态，避免误删尚未确认的工作：

```powershell
powershell -ExecutionPolicy Bypass -File tools\uninstall.ps1
```

只有明确不再需要任何运行状态时才使用：

```powershell
powershell -ExecutionPolicy Bypass -File tools\uninstall.ps1 -RemoveState
```

发布包旁会提供 `SHA256SUMS`。解压后先用 `Get-FileHash .\ppt-agent.exe -Algorithm SHA256` 与该文件核对；源码树中的可执行文件位于 `dist\ppt-agent.exe`。项目许可证和第三方声明分别见根 `LICENSE` 与 `THIRD_PARTY_NOTICES.md`；若发布包缺少根 `LICENSE`，不得对外分发。

## 开发环境

```powershell
uv venv .venv --python 3.12
uv pip install --python .venv\Scripts\python.exe -e ".[dev]"
.venv\Scripts\ppt-agent.exe --pretty doctor
```

## 标准闭环

```powershell
ppt-agent inspect deck.pptx --for text-edit
ppt-agent schema apply --op set_text
ppt-agent --pretty apply deck.pptx patch.json
ppt-agent --pretty qa deck.agent.candidate.pptx --profile presentation --suggest-fixes
ppt-agent --pretty render deck.agent.candidate.pptx
ppt-agent --pretty accept deck.agent.candidate.pptx --revision sha256:... --review-token ...
```

原件 `deck.pptx` 永不覆盖。修改先发布到 `deck.agent.candidate.pptx`，只有带匹配 revision 和 review token 的显式 `accept` 才提升为 `deck.agent.pptx`。

## v0.2.4b1 稳定性收口（schema_version 2.1）

- WAL 对 action/status、必需 revision 和派生临时路径执行 fail-closed 校验；损坏日志不会触碰源文件、candidate、accepted 或正式状态文件。
- 兼容只读 inspect 上无害的风险参数和常见 animation 字段别名；revision 冲突返回可直接执行的 candidate 修正命令。
- inspect/diff/qa/render 在产生 revision-bound 结果前后复核 revision，并发修改会明确返回 `REVISION_CONFLICT`。
- `doctor` 将 WPS COM 与 `pdftoppm` 都列为正式 render 的必需条件，并保留结构化 WPS COM 失败原因。

## Patch 示例

```json
{
  "request_id": "demo-001",
  "document_id": "inspect 返回的 document_id",
  "revision": "inspect 返回的 revision",
  "operations": [
    {"op": "set_text", "object": "s0:s2", "text": "新标题"},
    {"op": "add_animation", "object": "s0:s5", "effect": "fade", "trigger": "on_click"},
    {"op": "add_animation", "object": "s0:s3", "effect": "appear", "trigger": "with_previous", "paragraphs": "all"}
  ]
}
```

对象 ID 和 revision 只在同一结构版本内可靠。不要搜索项目源码猜参数，先运行单项 Schema：

```powershell
ppt-agent schema apply --op move
ppt-agent schema apply --op swap_image
ppt-agent schema apply --op add_animation
```

`ppt-agent schema apply` 默认只返回紧凑操作目录和 `use_when`；确定操作后再使用 `--op <name>` 查询单项契约。只有调试时才使用 `schema apply --full` 读取完整联合 Schema。

每个单项结果都包含必填/可选字段、约束、单位、最小示例、常见错误和是否经过 WPS。`inspect --for text-edit|layout|animation` 只返回任务相关字段；也可用 `--slide 2 --fields text,geometry` 精确投影。完整结构仍需显式 `--verbose`。

Patch JSON 接受 UTF-8 与带 BOM 的 UTF-8。`request_id` 可省略，CLI 会根据文档、revision 和 operations 生成稳定幂等 ID；如误传 operations 数组或错误的 inspect 字段，错误 JSON 会返回可直接复制的 `corrected_example`。

`qa --suggest-fixes` 只为越界和字号过小等确定性问题返回可执行 `suggested_patch`，不会修改文件或自动 accept。

逐段动画只接受 `paragraphs: "all"`：CLI 只调用一次 WPS `AddEffect`，由 WPS 按段落展开。旧 `paragraph` 字段不再接受；同一对象的重复动画或整体/逐段进入动画冲突会在 WPS 启动前返回 `DUPLICATE_ANIMATION`，原件、candidate 和请求状态均不变化。

该破坏性动画契约修正将 JSON `schema_version` 升级为 `2.0`。

## v0.2.3 协议收紧与切换保真（schema_version 2.1）

- 混合批次按声明顺序交替执行引擎与 WPS 操作；批次以引擎操作结束时追加 WPS 保存。WPS 是最终保存环境：WPS 保存后允许的唯一例外是对目标页 slide XML 做外科式切换属性恢复（WPS 会归一化丢弃 `spd` 与 `dir/orient`），随后必须用 WPS 只读重开验证最终字节，且验证前后哈希不变，否则不发布。
- 输入校验收紧并同步进机器 Schema（`schema apply --op` 返回的 JSON Schema 含 `oneOf`/`if-then`）：`swap_image` 新增 `slide` 字段且 `object/media/rid` 三选一；`add_shape` 的 line 不接受 `text` 且几何由 `from/to` 表达；富文本段落 `text`/`runs` 互斥、`runs` 非空；`set_theme` 至少一种非空颜色或字体；`add_table.fills` 与 `rows` 逐格同形、`col_widths` 数量等于列数；transition 的 `dir/orient` 按类型校验。
- 可选字段显式传 `null` 视为省略；机器 JSON Schema（含 `oneOf`/`if-then` 与 `additionalProperties: false`）与 Pydantic 对合法/非法输入结论一致，由标准 JSON Schema validator 逐样例验证。
- WPS 写入的 `mc:AlternateContent` 切换效果现在可被 `inspect`/`diff` 正确读取，`set_slide` 能替换或删除它。WPS 保存会归一化切换属性（丢 `spd` 与 `dir/orient`），适配层在发布前按补丁恢复，避免静默降级。

## v0.2.2 Agent 输入兼容

`inspect --fields` 接受常见自然别名：`slide_index`、`shape_id`、`object_id` 始终作为 identity 返回；`x/y/width/height` 自动映射到 `geometry`；`shape.*` 与 `slides.shapes.*` 返回紧凑对象视图。`--for content|edit|layout|animation` 已覆盖的冗余对象字段会被安全忽略，真正无法识别的字段才返回最接近候选。

所有编辑型定向检查（`--for text-edit|content|edit|layout|animation`）都会返回绑定当前 `document_id` 和 `revision` 的小型 `patch_template`，以及可直接拼到当前可执行文件后的 `apply_contract.argv_after_executable`。若文档包含受保护特性，契约同时列出需要用户明确授权的风险类型。完整 PatchRequest 可通过以下任一方式提交：

```powershell
ppt-agent apply deck.pptx patch.json
ppt-agent apply deck.pptx --patch patch.json
Get-Content patch.json -Raw | ppt-agent apply deck.pptx -
```

Windows Agent 应优先使用 `--patch patch.json`。只有调用环境能可靠保留 stdin 时才使用 `-`；不要用 PowerShell here-string 直接拼接 JSON。`inspect` 若报告受保护风险，确认任务确实要求保留后，再把报告中的风险类型显式传给 `--allow-risk`。

CLI 不接受内联 JSON，也不会把裸 operations 数组自动绑定到当前 revision；缺少 `document_id` 或 `revision` 的输入仍在 WPS 启动前拒绝。

## 安全默认值

- 宏、ActiveX、OLE、外部关系和远程媒体默认阻断写入与渲染。
- 只接受本地素材；CLI 本身不搜索或下载素材。
- WPS 使用独立 COM 实例，命令结束只关闭该实例。
- 第三方引擎固定到 `EveryInc/hands-on-deck@a24b996ecff6393ccf39c4fee2b88c493fb0b693`，许可证见 `vendor/hands_on_deck/LICENSE`。

## 当前 MVP 边界

已实现 13 个顶层命令、按操作区分的强类型 Schema、任务定向 inspect、QA 修复建议、批量原子 patch、revision、candidate、幂等请求、文档锁、安全扫描、WPS 动画/切换/图表标题、渲染、review token、accept/discard、模板 sidecar 与缓存管理。

复杂动画路径、SmartArt/OLE/媒体编辑、逐字动画和复杂图表明确返回 `UNSUPPORTED_OPERATION`，不会静默降级。

遇到明确不支持的能力时，CLI 不会自行切换工具。Agent 应先向用户说明不支持项与额外成本，得到明确同意后再回退旧 `pptx` skill；不得在未授权时搜索或加载旧 skill 文档。

## 协作修复 Bug

这是一个用于协作修复问题的私有仓库。欢迎同学帮忙复现、定位和修复 Bug。

提交问题时，请尽量附上：

- 最小复现步骤、输入文件类型和完整命令；
- 实际结果、预期结果和相关错误输出；
- 运行环境（Windows、Python、WPS 版本）以及是否能稳定复现。

提交修复前，请先运行：

```powershell
.venv\Scripts\python.exe -m pytest -q
```

修复建议通过独立分支提交，并在 Pull Request 中说明根因、改动范围和测试结果。不要提交真实演示文稿、密钥、个人配置或 `results/local/` 下的本机实验资料。

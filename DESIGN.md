# ppt-agent-cli 设计规格

状态：MVP 设计冻结  
日期：2026-08-12  
目标环境：Windows，WPS Office 12.1.0.26895

## 1. 产品定位

`ppt-agent-cli` 是面向 AI Agent 的 WPS-first PPTX 命令行适配层。它把 PPTX 结构读取、确定性编辑、WPS 自动化、渲染和质量检查封装为紧凑、稳定、机器可读的接口。

可执行命令为 `ppt-agent`。

核心目标：

- 提高 Agent 从零制作、修改、审查和视觉迭代 PPT 的效率。
- 相比当前通用 `pptx` skill，默认流程至少减少 70% 的 PPT 结构与工具输出 Token。
- 让 Agent 在不理解 OOXML 或 WPS 内部对象模型的情况下安全完成高频操作。
- 将技术执行成功与用户验收明确分开，始终保留干净的返回点。

CLI 不内置大模型。内容创作、布局判断和设计意图推断由外部 Agent 完成；CLI 只负责确定性的读取、校验、修改、渲染和事实报告。

## 2. MVP 使用边界

第一版：

- 仅支持本机 Windows 环境。
- 强制要求安装已验证版本的 WPS。
- 允许 WPS 最小化或短暂显示，但不得抢焦点、等待交互弹窗或遗留进程。
- 以 WPS 中打开、编辑、播放和导出的效果为验收标准。
- 暂不测试或承诺 Microsoft PowerPoint 兼容性。
- 暂不支持跨平台、服务端运行和常驻后台服务。
- 先作为本地私有项目开发，但许可证与测试数据按未来可公开标准管理。

项目不是 LibreOffice CLI，也不绑定纯 UNO 或纯 OOXML。WPS 是第一版最终写入与验证环境。

## 3. 核心工作流

### 3.1 制作

```text
slide spec 或规范化模板
→ create 生成 candidate
→ inspect / render / qa
→ Agent 对 candidate 继续 apply
→ 用户预览并确认
→ accept
```

创建以语义化整页 spec 为主，绝对坐标 patch 仅用于精调。MVP 内置约 8 至 12 个可靠布局，并支持复制现有页面复用风格。

### 3.2 修改与审查

```text
inspect 已确认版本
→ 紧凑结构与问题摘要
→ apply 批量 patch 到 candidate
→ diff / 局部 render / qa
→ 继续修正 candidate 或 discard
→ 用户确认后 accept
```

### 3.3 人工修改同步

```text
baseline（用户最后认可的版本）
→ 用户在 WPS 中手动修改并保存
→ re-inspect
→ revision 冲突
→ CLI 输出结构化精简 diff
→ Agent 理解调整意图并重新规划
```

revision 防止 Agent 覆盖用户修改；re-inspect 提供当前状态；diff 提供事实变化；设计意图仍由 Agent 推断。

检测到冲突后不得自动重放旧 patch。

## 4. 状态模型

### 4.1 文件角色

```text
deck.pptx                  用户原件，永不覆盖
deck.agent.pptx            最近一次用户确认的工作版本
deck.agent.candidate.pptx  当前等待验收的候选版本
```

- `apply` 成功只表示技术执行成功，不表示用户认可。
- `inspect`、`diff` 和 `apply` 均不得推进 baseline。
- 只有显式 `accept` 才能将 candidate 提升为新的已确认版本并推进 baseline。
- `accept` 可原子覆盖上一份 `deck.agent.pptx`，但原件永远不动。
- candidate 只能由显式 `discard` 或 `apply --restart-from-baseline` 放弃。
- 不保留完整历史，不引入 Git 版本管理。

### 4.2 Baseline

baseline 表示用户最后认可的结构状态，不是历史快照。

- PPT 改名或移动后视为新文档并重置 baseline。
- 宁可丢失一次 diff，也不做模糊的文档自动认亲。
- baseline 只保留完成 diff 所需的紧凑结构。
- `--no-state` 允许纯无状态运行。

### 4.3 验收绑定

渲染或预览返回 `candidate_revision` 和 `review_token`。`accept` 必须同时匹配二者：

```bash
ppt-agent accept deck.agent.candidate.pptx \
  --revision sha256:... \
  --review-token ...
```

candidate 在预览后发生任何变化，token 立即失效并要求重新预览。存在 error 级 QA 问题时默认拒绝 accept；显式覆盖必须记录被接受的问题。

## 5. 运行时状态

运行状态统一存入：

```text
%LOCALAPPDATA%\ppt-agent\
  state\<document-id>\baseline.json
  requests\<document-id>\recent.json
  locks\<document-id>.lock
  transactions\<document-id>\journal.json
  renders\<document-id>\...
```

- `document_id` 由规范化绝对路径隔离。
- baseline 包含 `document_id`、`source_path`、`file_hash`、`revision`、`created_at` 和 `schema_version`。
- 客户文件目录中不创建隐藏运行状态。
- 模板 manifest 是用户资产，与模板 PPTX 放在一起。
- `cache status` 和 `cache clean` 用于查看与清理状态。
- 过期渲染自动淘汰。
- 文档锁带租约与 PID 复用检测：锁文件记录 token、PID、创建时间与租约时长；持有者死亡或 PID 被复用后经排他 guard 原子接管（guard 内重读并核对原锁，两个等待者不可能同时赢得锁）；真正存活的持有者绝不因时间过期被抢占；正常释放前校验 token 防止误删后继锁。
- `create` / `apply` / `accept` / `discard` 统一经 `TransactionCoordinator`（同一文档锁 → 入口崩溃恢复 → 重新读取状态 → journaled 提交 → 持久化结果 → 清理）。

## 6. 命令面

MVP 冻结为 12 个顶层命令：

| 命令 | 职责 |
|---|---|
| `doctor` | 检查 WPS、候选引擎、渲染依赖和版本 |
| `capabilities` | 返回紧凑能力索引和按需 Schema |
| `inspect` | 读取结构、对象、动画、安全风险和紧凑摘要 |
| `diff` | 比较 baseline、candidate 或指定文件的结构变化 |
| `create` | 根据 slide spec 或模板创建 candidate |
| `apply` | 事务式执行批量 patch |
| `render` | 导出 PDF、缩略图或指定页面高清图 |
| `qa` | 按 profile 运行结构与视觉规则 |
| `template` | `inspect / normalize / validate` 模板 |
| `cache` | `status / clean` 运行状态 |
| `accept` | 将已预览的 candidate 提升为确认版本 |
| `discard` | 安全放弃当前 candidate |

具体编辑动作统一作为 `apply` operation，不在 MVP 中扩张为顶层命令。

## 7. Agent 协议

### 7.1 输出

- `stdout` 永远只输出符合版本化 Schema 的 JSON。
- 人类提示与调试日志写入 `stderr`。
- 命令、字段、枚举和 `error_code` 使用英文。
- 可提供简短 `message_zh`，但 Agent 不应依赖自然语言解析。
- 成功和失败都返回 `document_id`、`revision`、引擎版本和 `wps_version`。
- 默认返回最小必要信息；`--pretty` 格式化，`--verbose` 展开诊断详情。

示例：

```json
{
  "ok": false,
  "error_code": "REVISION_CONFLICT",
  "message_zh": "候选文件已发生变化，请重新检查",
  "retryable": true,
  "next_action": "reinspect",
  "document_id": "uuid...",
  "current_revision": "sha256:..."
}
```

### 7.2 能力发现

```bash
ppt-agent capabilities
ppt-agent schema inspect
ppt-agent schema apply
ppt-agent schema operation:add_animation
```

完整命令参考不写入 Agent Skill。CLI 内置 Schema 是当前版本的唯一权威来源。

### 7.3 对象寻址

- 临时对象 ID 只在同一 revision 内可靠。
- patch 必须同时匹配 `document_id` 与 `revision`。
- 模板 placeholder 和明确 role 可作为受约束的语义选择器。
- 文本默认精确匹配，不做模糊猜测。
- 预期单对象却匹配多个时失败。
- 批量修改必须声明 `expect_count`，数量不符则整批回滚。

### 7.4 批量 patch

批量 patch 是核心接口，单操作命令未来只能作为语法糖。

```json
{
  "request_id": "uuid...",
  "document_id": "uuid...",
  "revision": "sha256:...",
  "operations": [
    {"op": "set_text", "object": "s3:o5", "text": "新标题"},
    {"op": "move", "object": "s3:o7", "dx": 20},
    {"op": "add_animation", "object": "s3:o5", "effect": "fade"}
  ]
}
```

- 所有 operation 预验证后按顺序执行。
- 任一步失败，整批不发布。
- `request_id` 必须幂等：成功重试返回原结果；执行中返回 `IN_PROGRESS`；同 ID 不同内容拒绝。
- 同一文档写操作串行，默认遇锁立即失败，可显式 `--wait`。
- revision 在取得锁后再次校验。

## 8. 编辑与保真规则

### 8.1 文本

- `replace_text` 只替换片段并尽量保留字符级样式。
- `set_text` 替换文本框内容并默认继承主样式。
- `set_rich_text` 显式提交段落和 run 样式。
- 任何可能重置格式的操作都必须返回 `format_impact` 并要求显式授权。
- 文本框级动画必须保留；逐段动画受段落数影响时先警告或拒绝。

### 8.2 支持能力

MVP 完整支持：

- 幻灯片增删、复制、排序；
- 富文本、图片、基础形状、表格；
- 移动、缩放、对齐、分布和层级；
- 备注、超链接、基础布局与主题样式；
- 柱状图、折线图、饼图，且必须是 WPS 可编辑的原生图表；
- 图表创建、数据更新、标题、图例和颜色调整；
- 对象级和逐段动画：`appear / fade / fly_in`；
- 动画时序：`on_click / with_previous / after_previous`；
- 动画顺序、方向、持续时间和延迟；
- 切换：`none / fade / push / wipe`，默认不主动添加。

图表动画 MVP 仅支持整体出现，禁止静默降级为图片。

### 8.3 识别但暂不编辑

- SmartArt；
- 音频、视频、3D；
- 公式、OLE、宏和 ActiveX；
- 复杂动画路径、逐字动画、交互触发器和复杂动画链；
- 复杂组合图、双轴、瀑布图等；
- 高级母版和 PowerPoint 专有行为。

未知或不支持对象必须原样保留并标记 `editable: false`。无法可靠保留时默认阻断编辑，绝不静默破坏。

Agent 不得使用公开的 `xml set`。可提供只读 `debug xml get` 诊断入口；所有正式修改必须经过类型化 patch。

## 9. 模板

MVP 支持用户提供普通 PPTX 模板，并由 Agent 辅助规范化：

```text
客户原始 PPTX
→ inspect + render
→ Agent 提交 placeholder mapping
→ CLI 验证
→ 用户确认或显式 --accept
→ 输出 normalized.pptx + normalized.template.json
```

- 源模板永不覆盖。
- 占位符映射默认要求人工确认。
- 不明确的对象标记为 `unresolved`，不得猜测删除。
- MVP 不建立全局模板库。
- 使用时显式传入 PPTX 和 sidecar manifest。
- 后续版本再研究自动理解没有标记的任意模板。

## 10. 检查、渲染与 QA

### 10.1 分层读取

- `inspect` 默认直接解析 OOXML，不启动 WPS。
- `qa` 先运行结构规则，需要真实排版或字体结果时再调用 WPS。
- `render` 使用 WPS 导出 PDF，再转换为 JPEG。
- `apply` 发布前执行结构验证，WPS 是最后写入和最终验证者。

### 10.2 Token 策略

- 初次默认 inspect 输出不超过约 4 KB。
- 默认生成整套低分辨率缩略图总览。
- 只为新增、修改或告警页面生成高清图。
- 修复后只复查受影响页面。
- 最终交付前执行一次全量 QA。
- 未修改页面不重复输出完整对象。
- QA 默认只返回问题，无问题页面只返回计数。

### 10.3 QA profile

- `basic`：溢出、越界、缺失素材等客观错误，默认 profile。
- `presentation`：增加字号、文字密度、视觉层级和远距离可读性规则。
- `assignment`：允许更多正文，强调结构、引用和内容完整性。

QA 默认只诊断。只有少量高置信、确定性规则允许显式 `--fix`；字号缩小、布局重排、删除内容、替换字体和动画调整必须由 Agent 提交 patch。

## 11. 安全与隐私

- `inspect` 在启动 WPS 前静态扫描宏、ActiveX、OLE、外部关系和远程媒体。
- 高风险特性默认阻断，按类型显式 `--allow-risk` 才能放行。
- 禁止自动执行宏和更新外部链接。
- CLI 只接受本地素材并默认嵌入 PPTX。
- CLI 不联网搜索、下载素材或安装字体。
- 普通日志不记录正文、备注、图片内容或完整 patch。
- 默认路径日志只保留文件名；绝对路径仅在 debug 中显示。
- baseline 文本优先存哈希和短预览，而不是全文。
- 第三方引擎固定 commit 或 release，关闭自动更新和联网；升级必须重新审计和回归。

CLI 处理未知操作时必须保持文件不变：

```json
{
  "ok": false,
  "error_code": "UNSUPPORTED_OPERATION",
  "capability": "motion_path_animation",
  "document_unchanged": true,
  "fallback": {
    "strategy": "external_pptx_workflow",
    "reason": "typed patch support is unavailable"
  }
}
```

CLI 只建议回退到原 `pptx` skill、WPS 手工操作或专用工具，未经用户同意不得自动执行高成本备用方案。

## 12. 写入事务与 WPS 生命周期

```text
复制 baseline 或当前 candidate 到临时工作副本
→ 上游引擎执行普通编辑
→ 静态验证
→ WPS COM 执行动画、切换等专属操作
→ WPS 保存并重新打开验证
→ inspect + QA
→ 全部成功后原子发布 candidate
```

- WPS 是事务的最终保存环境；WPS 保存/执行结束后原则上不再修改文件。
- 唯一受限、可审计的例外：WPS 保存会归一化切换属性（丢失 `spd` 与 `dir/orient`）。适配层随后只对目标页 slide XML 做外科式 ZIP/XML 修改，恢复补丁声明的切换属性；其余 ZIP 条目字节不变。
- 任何后处理发生后，必须以 WPS 只读方式重开验证最终字节；验证前后计算文件哈希，若只读验证改变文件则不得发布。
- 最终重开失败时：不发布 candidate、不记录成功请求状态、原件与既有 candidate 保持不变、清理全部临时文件。
- 响应中的 `wps_version` 来自最终验证步骤。
- 每批 patch 只发布一次。
- candidate 发布与幂等请求记录通过事务日志保证一致性。WAL 四态：`prepared`（发布状态未知，只能回滚）、`rollback_pending`（回滚决定已持久化，继续回滚）、`committed`（补齐 record，不再回滚）、`cleanup_pending`（业务已成功，仅清理，不得报业务失败）。
- journal 写入后的任何异常（publish/refresh/committed/record）都会先把回滚决定原子写入 `rollback_pending` 再执行回滚；**状态转换必须先于文件副作用**——`rollback_pending` 持久化失败时不修改任何文件，保留原 WAL 由恢复器收敛。回滚成功才清 journal，失败则保留 WAL 由下次入口继续。恢复动作逐文件独立、幂等（accepted 与 candidate 各自按自身状态恢复）。
- 进入最终提交点（record 成功）后，清理类失败（cleanup/clear journal）只留下可恢复 WAL（committed/cleanup_pending）并在 stderr 记录诊断，**不得改变本次业务结果**。
- 崩溃恢复在下一次取得文档锁时执行：`prepared`/`rollback_pending` → 回滚；`committed` → 保留结果、补写记录（accept 以 journal baseline 为权威，revision 不一致时原子覆盖）；`cleanup_pending` → 只清理。
- 事务日志 fail-closed：journal 存在但无法解析，或 status/action/必需字段/路径不合法（路径必须位于文档目录或状态目录内）时返回 `TRANSACTION_JOURNAL_CORRUPT` 并禁止写入，原文件保留供诊断，绝不猜测恢复策略。
- `apply` 的规划、执行、验证与提交职责分离：`ExecutionPlan`（Planner 按 registry 的 backend 与 reducer 生成有序步骤和最终 transition Postcondition）、引擎/WPS 执行器、`validate_pptx` + WPS 只读重开验证器、带日志的事务协调器。
- 命令结束时只关闭 CLI 自己启动的 WPS 实例。
- 每个阶段有明确超时。
- 超时先正常关闭，仍无响应时只终止记录 PID 的本次实例。
- 永不按进程名批量结束 WPS。
- 写入阶段失败不自动重试；只读打开或导出最多自动重试一次且必须幂等。
- 失败时不发布 candidate。

## 13. 技术方案

首选实现：

- Python 3.12；
- `pywin32` 调用 `KWPP.Application` COM；
- OOXML/ZIP 层负责静态读取、diff、安全扫描和完整性验证；
- Pydantic 定义 patch、命令输出和版本化 Schema；
- 项目独立 `.venv`，不使用与 Hermes 共用的环境；
- 最终打包为独立 `ppt-agent.exe`。

候选上游引擎：

- `EveryInc/hands-on-deck`：优先评估其原子 patch、inspect、diff、lint 和局部渲染设计。
- `iOfficeAI/OfficeCLI`：优先评估其 OpenXML 能力、动画、Schema 和单文件分发。

采用稳定的 `ppt-agent` 外壳，内部引擎固定版本。优先薄适配；只有确认必须修改核心逻辑时才 fork，并保留许可证、来源 commit 和修改说明。

## 14. 配置与安装

配置优先级：

```text
命令行参数
→ 项目目录 ppt-agent.toml
→ 程序安全默认值
```

MVP 配置只包含少量稳定选项，例如 QA profile、候选后缀、渲染 DPI 和状态目录。WPS 路径与版本由 `doctor` 自动发现。

开发阶段使用独立 `.venv`；发布时生成单文件 EXE，安装到 `%LOCALAPPDATA%\Programs\ppt-agent\`，只修改当前用户 PATH，不要求管理员权限。缺失依赖只诊断，不静默安装。

## 15. 测试与验收

测试分层：

- 单元测试：Schema、revision、diff、安全扫描、命名、状态机。
- 文件集成测试：inspect、原子 patch、格式与不支持对象保留。
- WPS 实机测试：动画、切换、图表、PDF 导出、弹窗、超时和进程清理。
- 黄金测试：结构摘要与渲染图的可解释差异。

每次发布前必须跑 WPS 冒烟测试和六场景 A/B 基准。测试不得调用或关闭用户已有的 WPS 实例。

六个 A/B 场景：

1. 从零制作 8 至 10 页演讲稿。
2. 使用客户模板制作作业汇报。
3. 修改已有 PPT 的文字、图片和布局。
4. 审查并修复多页排版问题。
5. 添加对象级与逐段动画。
6. 根据人工调整 diff 继续完善其他页面。

对比原 `pptx` skill，记录输入/输出 Token、工具调用次数、总耗时、WPS 打开与播放结果、遗漏或误改数量以及人工返工次数。

MVP 通过线：

- 默认流程的 PPT 结构与工具输出 Token 至少降低 70%。
- 六类任务均可交付。
- 不比原流程产生更多文档损坏或明显视觉问题。
- 简单动画是 WPS 路线的硬性 PoC 门槛。

## 16. Agent Skill

随 CLI 提供一个精简 Skill，只说明：

- 何时优先使用 `ppt-agent`；
- `inspect → apply → qa/render → accept` 标准闭环；
- 安全规则、candidate 语义和降级条件；
- 使用 `capabilities` 和按需 Schema；
- 不复制完整命令参考。

## 17. 非目标

MVP 明确不做：

- 版本管理、Git 集成和历史恢复系统；
- 内置模型、联网搜索或素材生成；
- 任意 OOXML 写入逃生口；
- 自动接管正在 WPS 中打开的文件；
- 常驻 WPS daemon；
- 全平台与所有 WPS 版本兼容；
- 自动理解任意无标记模板；
- 未列入冻结范围的高级对象编辑。

## 18. 决策原则

- 真实目标是提高 Agent 的 PPT 交付效率，而不是从零重写 PPTX 引擎。
- 先验证成熟开源项目，能薄封装就不 fork，能复用就不重写。
- 普通演讲和作业场景优先；高级能力按真实频率逐项测试后加入。
- 不认识的对象必须保留；无法保证时明确失败。
- 技术成功不代表用户认可，只有显式 accept 才推进 baseline。
- PoC 失败时停止并重新决策，不靠扩大代码量掩盖路线问题。

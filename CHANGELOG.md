# Changelog

本文件记录面向用户的行为变化。发布日期以最终发布标签为准。

## 0.2.4b1 - 2026-08-21

### Fixed

- `accept` 现在只接受规范的 `.agent.candidate.pptx` 候选路径，避免误将原件或已接受工作版移动、删除。
- 修正 WPS 的 `wipe` 切换常量，不再错误保存为 `push down`。
- 事务日志改为严格校验 `status`、`action`、必需 revision 与派生临时路径，损坏或被篡改的 WAL 会 fail closed，不再猜测恢复动作。
- 收紧 Agent 调用协议的结构化纠错，保留 revision、candidate、review token 与显式风险授权边界。
- `doctor` 将 PDF 渲染器纳入健康门槛，并返回结构化 WPS 探测错误。
- `inspect`、`diff`、`qa` 和 `render` 在发布结果前复核 revision，避免并发修改下发布混合快照。

### Release work

- 增加 Windows 按用户安装与卸载脚本。
- 增加发布检查清单和第三方组件声明。
- 补充安装、卸载以及明确不支持能力的回退说明。
- EXE 写入 Windows FileVersion/ProductVersion，并生成内容寻址的 release-candidate freeze。

## 0.2.3 - 2026-08-14

### Added

- Schema `2.1`：按操作导出的强类型 JSON Schema、紧凑 capabilities 和任务定向 inspect。
- WPS 动画、切换、图表标题、PDF render、review token、accept/discard 与事务恢复闭环。
- 混合引擎/WPS 操作按声明顺序执行，并在 WPS 保存后保真恢复切换属性。

### Changed

- 逐段动画公开语义统一为 `paragraphs: "all"`，旧 `paragraph` 字段不再接受。
- Patch 支持 UTF-8 BOM、稳定自动 `request_id` 和可复制的结构化纠错示例。

### Validation status

- 自动测试和六场景产物质量通过；真实 WPS 合成稿动画、切换和 accept 闭环通过。
- 该轮 Agent 协议验收仍记录 3 次可自愈错误调用，未缓存输入加输出降幅为 64.76%，因此 0.2.3 未作为 Beta 发布。

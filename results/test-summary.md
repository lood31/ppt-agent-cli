# 验证摘要

日期：2026-08-12

- 项目单元与文件集成测试：11/11 通过。
- WPS COM 硬门槛：通过。
- 产品 E2E：`inspect → apply → qa → render → accept` 通过。
- 原件 SHA-256 在 apply/accept 后保持不变；candidate 被 accept 后删除，agent 工作版哈希与已预览 revision 一致。
- 动画保留：原有 1 个 + 新增 1 个，WPS 重开后计数为 2。
- 图表：WPS 重开后仍为原生图表，标题修改可读。
- WPS PDF 导出与 JPEG 转换：4/4 页通过。
- 内置创建布局：WPS 保存重开后 `presentation` QA 为 0 error / 0 warning。
- 上游 hands-on-deck 核心测试：40/41 通过；唯一失败为其 LibreOffice render 测试，产品正式 WPS render 不使用该路径。
- 单文件 EXE：`doctor`、`inspect`、`apply`、`qa` 通过；EXE 写入的动画经 WPS 重开后仍保留。
- 发布文件：`dist/ppt-agent.exe`，SHA-256 `E5043916BCDFA96754812329E8B41B11234239414BD95F697ED43D84EB33363D`。

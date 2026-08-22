# Token 与 Agent 可用性烟雾测试

日期：2026-08-12

## 结果

- 默认 `inspect` 使用 one-line-per-shape 紧凑结构，不输出 XML。
- 4 页合成稿默认 JSON 输出为 1,198 bytes（约 300 tokens）；`--verbose` 为 2,409 bytes（约 603 tokens）。
- 单对象修改 E2E 使用 `inspect → apply → qa/render` 三阶段。
- Patch 包含 4 个操作：文本、移动、动画、图表标题；无需完整文档 dump。
- `qa` 无问题时只返回计数和空 issues。
- `render --pages N` 可只生成单页；修复后无需重复输出未修改对象。

结论：协议设计具备达到 70% Token 降幅的现实基础，但设计规定的正式 70% 指标必须等六场景 A/B 才能宣称达标；本次不把烟雾测量冒充正式基准。

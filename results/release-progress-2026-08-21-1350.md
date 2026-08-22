# v0.2.4-beta.1 发布收口进度（2026-08-21）

## 当前结论

代码、事务、协议、本机 WPS 闭环和 release-candidate 包已经完成并通过本地验证；**尚不能对外宣称正式 Beta 已发布**。剩余门槛需要用户授权或真实材料，不能由本轮自行假设。

## 已完成

- 版本：Python/CLI `0.2.4b1`，发布显示名 `0.2.4-beta.1`；Schema 保持 `2.1`。
- WAL fail-closed：显式校验 action/status、必需 revision、action-specific 临时/备份路径；损坏或恶意 journal 不触碰正式文件。
- Agent 协议：兼容 inspect 的无害 `--allow-risk`、动画自然字段别名、结构化 revision conflict 修正路径；安全授权和 revision 绑定未放宽。
- 只读一致性：`inspect`、`diff`、`qa`、`render` 在发布结果前复核 revision；未实现没有收益的全局读锁。
- `doctor`：把 `pdftoppm` 纳入健康门槛，并返回结构化 WPS 探测错误。
- Windows EXE VersionInfo：FileVersion/ProductVersion 为 `0.2.4-beta.1`。
- 安装、卸载、CHANGELOG、第三方声明、发布检查清单和回退说明已补齐。

## 验证证据

- 最终全量测试：`597 passed in 36.65s`。
- 新 EXE `doctor`：`healthy=true`，WPS `12.0`，`wps_com=true`，`pdftoppm` 可用。
- 真实 WPS 合成稿闭环：
  - apply 两项操作成功，candidate revision 为 `sha256:c4d85820fd4fd153e14ee5422cffc253c392c2c7bd7e6e24f1a4c54bdfbb5a0c`；
  - WPS 只读重开：第一页恰好 1 个动画，`effect_type=10`、`trigger=1`；第一页切换 `EntryEffect=3852`；
  - render 4 页成功，QA 0 error / 0 warning；逐张原图视觉 QA 4/4 通过；
  - accept 成功，`original_unchanged=true`；accepted 再次由 WPS 重开后动画、切换和 SHA-256 均保持不变。
- 隔离安装→`--version`→卸载通过，安装目录已清理。
- 解压 RC 包后 `--version` 和单项 Schema 冒烟通过。
- 内容冻结共校验 34 项，哈希不匹配为 0。

## 冻结与产物

- EXE：`dist/ppt-agent.exe`
  - SHA-256：`df87346bd55c13df39bbd0a4d521e902091d2bd6b276679fdbcd70127c4b72f3`
- RC 包：`dist/ppt-agent-0.2.4-beta.1-windows-x64-rc.zip`
  - SHA-256：`ccbd40c7235c84d9be341d9da867938fe2d13c784755f09bc21d98bf7ee0fb50`
- 校验和：`dist/SHA256SUMS`
- 内容冻结：`acceptance/freeze/v0.2.4-beta.1/`
- WPS 证据：`results/local/beta-release-v024b1/wps-closure/`

## 未完成且阻断正式发布

1. **六场景 B-only 零误调用复测未执行。** 执行请求被安全审查拒绝：它会把本地 PPT、图片和任务内容发送到外部 GPT-5.4 API 并计费。需要用户明确同意这些具体验收素材向该 API 出境后才能运行。
2. **三轮稳定性门槛尚无本版本证据。** 即使下一轮通过，仍需按既定门槛补足三轮并报告均值、中位数、最低降幅和质量通过率。
3. **3–5 份脱敏真实 PPT 试用缺失。** 当前仅证明合成稿闭环，不能替代真实演讲稿、作业、模板和人工续改试用。
4. **根 LICENSE 未选择。** 这是版权所有者决定；在根 LICENSE 缺失时不得对外分发。
5. **无独立 Git 溯源。** `ppt-agent-cli-main` 没有自己的 `.git`，外层仓库仅把整个目录视为未跟踪文件，因此当前只能称内容寻址冻结，不能声称 commit/tag 发布。

## 下次继续顺序

1. 用户明确选择项目许可证和唯一 Git 仓库根。
2. 用户明确授权六场景具体素材发送到 GPT-5.4 API 并产生费用后，先跑一轮 B-only；不达标先分析，不追加两轮。
3. 首轮达标后补两轮独立复测。
4. 完成 3–5 份脱敏真实 PPT 的 inspect→apply→WPS 回开→qa→render→人工预览→accept/discard 闭环。
5. 全绿后重新生成最终（非 RC）包、freeze、SHA256，commit 并打 `v0.2.4-beta.1` 标签。

停止原因：本地可自主完成的发布工作已经完成；剩余项需要外发授权、许可证选择、Git 决策或真实试用材料。

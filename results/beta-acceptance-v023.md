# Beta 前验收：v0.2.3

日期：2026-08-14

冻结版本：`0.2.3`

Schema：`2.1`

六场景运行：`results/local/token-api/api-gpt54-b-v023-zero-invocation-r1/`

真实 WPS 闭环：`results/local/beta-acceptance-v023/wps-closure/`

## 总结

本轮不能进入 Beta。PPT 质量、真实 WPS 动画/切换和 accept 事务闭环均通过；但 Agent 零误调用协议和“未缓存输入 + 输出降低至少 70%”两项未通过。

| 验收项 | 结果 | 证据摘要 |
|---|---|---|
| 版本与 Schema 冻结 | 通过（内容寻址） | 产品 0.2.3；Schema 2.1；源码树、EXE、capabilities、完整 apply Schema 均有 SHA-256 |
| 全量自动测试 | 通过 | Python 3.12.13；`577 passed in 51.65s` |
| 六场景产物质量 | 通过 | 6/6 输出存在；QA 0 error；WPS 回开 6/6；28/28 页最终视觉通过 |
| 总 Token 降幅 | 通过 | A 7,595,417；B 1,878,179；降低 75.27% |
| 未缓存输入 + 输出降幅 | **失败** | A 555,801；B 195,875；降低 64.76% |
| Agent 错误调用 | **失败** | 3 次非零 CLI 调用，目标为 0 |
| 单次文本输出 | 通过 | 最大 9,827 B，小于 64 KB |
| 禁止搜索 | 通过 | 源码、memory、旧 skill、递归搜索均为 0 |
| 安全/误改事故 | 通过 | 0 |
| 真实 WPS 动画/切换/accept | 通过 | WPS 12.0；原件不变；candidate、review token、accept、baseline、WAL 收敛完整 |

## 冻结证据

- 源码树 SHA-256：`ce1bbdebd8b8e94dcfb25523d45bba59c8016d4e4ee91989e515743a285ad12f`
- EXE SHA-256：`9825ce12fb2e05c5e3a0fc5820ed4f770d59adf1d9ce0fa6acd3f58cf56a2cb5`
- capabilities SHA-256：`a6a809ddfa4d9e2c39ad7b10733e39edffd8155beb9a6f74cbb8d8b31714237d`
- 完整 apply Schema SHA-256：`3cc3dd898ac23e8203dd6842aca51743429c5f7113218a209f27b40f82b8a263`
- 冻结清单：`acceptance/freeze/v0.2.3/freeze-manifest.json`

项目搬运时没有包含独立 `.git`，因此本轮完成的是可核验的内容寻址冻结，不是 Git commit/tag 冻结。不得把外层仓库的 `1d7200a` 误认为本目录的版本提交。

封存 A 基线 `api-gpt54-final` 已离线校验，六场景输入、事件、输出、协议和 Codex CLI `0.142.3` 均匹配，没有重跑 A。

## 六场景 B-only

| 场景 | B 总 Token | 工具调用 | 耗时（秒） | 进程/产物 | 质量 |
|---:|---:|---:|---:|---|---|
| 1 | 184,135 | 16 | 89.219 | 0 / 存在 | 通过 |
| 2 | 287,451 | 14 | 117.141 | 0 / 存在 | 通过 |
| 3 | 538,488 | 18 | 180.022 | 0 / 存在 | 通过 |
| 4 | 255,860 | 14 | 124.825 | 0 / 存在 | 通过 |
| 5 | 295,491 | 14 | 110.895 | 0 / 存在 | 通过 |
| 6 | 316,754 | 22 | 157.190 | 0 / 存在 | 通过 |

合计 98 次工具调用，Agent 场景耗时 779.292 秒。

### 三次错误调用

1. 场景 3 给只读 `inspect` 传了 `--allow-risk external_relationship`，argparse 返回 `INVALID_ARGUMENT`。
2. 场景 3 已从 candidate inspect 得到绑定 candidate revision 的 patch 和正确 `apply_contract`，但仍把 patch 传给原始 `source.pptx`，正确触发 `REVISION_CONFLICT`；随后改用 candidate 路径成功。
3. 场景 5 把 `effect,trigger,paragraphs` 当成 inspect 字段，返回 `INVALID_INSPECT_FIELDS`；随后使用 `animation,name,text,type` 成功。

这三次均为可自愈协议摩擦，没有造成误写；revision 冲突证明安全边界有效，但“错误调用为 0”的验收标准仍然失败。

## 质量与视觉

- 六场景 `qa --profile presentation` 均为 0 error；场景 1 有 14 条 warning，其余为 0。
- WPS 12.0 成功只读回开 6/6，页数为 8、4、4、4、4、4。
- 场景 1 八页标题全部匹配输入。
- 场景 2 指定标题、正文、按钮、表格和后三页标题全部存在。
- 场景 3 标题 x=0.95 英寸，替换图片二进制匹配。
- 场景 4 标题 x=0，字号 32pt。
- 场景 5 第一页恰好 4 个动画效果：1 个 fade/on_click，加上由单次逐段语义展开的 3 个 appear/with_previous；段落范围为 0、1、2。
- 场景 6 第二页标题 x=1.05 英寸，文字匹配任务。

独立视觉代理逐张检查了 28 页。其最初报告场景 2–6 的柱状图标签错位；主验收随后对五个精确 `slide-2.jpg` 分别单文件、原始分辨率重开，其中偶发空白预览再次重开，最终 A/B/C 均位于对应柱下方。该项属于已知预览显示误报，不是文件缺陷。最终视觉结论为 6/6 PASS。

## 真实 WPS 动画、切换与 accept 闭环

独立合成稿闭环未复用六场景 candidate：

1. inspect 返回 document_id、revision、风险授权和 revision-bound patch template。
2. apply 在 WPS 12.0 中写入 `fade/on_click` 动画和第一页 `wipe` 切换，生成 candidate。
3. 原件 SHA-256 始终为 `38954b12b20245baf76fb944ba2572a6f2c585007cac067182ca732abeada23e`。
4. candidate SHA-256 为 `6f9fa8d257ed79c19fc6febc971ccd9f90ca86841d8dfe4b6d2bb6de9cded736`。
5. WPS COM 结构读取：动画 `effect_type=10`、`trigger=1`；切换 `EntryEffect=3852`（wipe）。
6. render 返回 4 张预览、0 个基础 QA issue 和 review token。
7. accept 后 accepted 哈希与 candidate 相同；原件不变；candidate 不存在；journal 不存在；baseline revision 已推进到 accepted 哈希。
8. accepted 再次由 WPS 12.0 回开，动画和切换结构保持不变。

## 只读命令强一致性决策

**本轮不实现全局只读强一致性锁。**

理由：写路径使用文档级锁、WAL 和原子替换；apply/accept 的 revision 与 review token 会阻止陈旧结果提交。本轮 577 个测试、六场景和真实 accept 闭环没有出现读写竞态或误提交。给全部 inspect/diff/qa 增加排他锁会增加等待与失败面，却不解决当前 Beta 的真实阻断项。

保留一个定向 P2：`qa --suggest-fixes` 和 `render` 会生成 revision-bound 后续动作，未来若支持同一文档被多个 Agent 并发操作，应在读取前后校验 revision，或使用共享读锁/一致性快照；纯 inspect/diff/qa 继续采用乐观读即可。

另一个已知、与本轮决策分离的 P2 仍然存在：`txn.py` 对缺失的 `status`/`action` 仍有默认值，apply journal 未强制 `new_revision`，路径校验仍是目录级而非精确派生文件白名单。本轮没有重分类为 P1，也没有把它混入“只读强一致性”范围；公开发布前应单独修复并复跑 WAL 恢复测试。

## 决策

- 不发布 Beta，不补跑第二、第三轮。
- 不处理全局只读强一致性。
- 下一步只针对三类确定性协议摩擦做最小修复：只读命令上的无害风险参数、animation 字段别名、candidate-bound patch 的纠正 argv。
- 修复后只跑一轮完整 B-only；必须同时达到零错误调用和未缓存输入 + 输出降低至少 70%，才进入后两轮稳定性复测。

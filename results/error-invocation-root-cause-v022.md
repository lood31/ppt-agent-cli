# v0.2.2 错误调用根因审计

日期：2026-08-13

证据来源：`api-gpt54-b-v021-zero-errors-r1` 六场景事件流。本文仅使用本地日志、单元测试和 EXE 回放，没有调用模型 API。

## 结论

13 次非零退出不是 PPT 编辑引擎故障，也没有造成文档误改。它们来自三层接口错位：自然语言任务与操作枚举混用、编辑上下文没有随每种定向 inspect 一起返回、Windows 命令宿主不能可靠转发 PowerShell here-string stdin。风险阻断则按设计工作，但此前 inspect 没有给出可直接复用的参数数组。

## 失败分解

| 数量 | 表象 | 根因 | v0.2.2 处理 |
|---:|---|---|---|
| 6 | here-string 传入 `apply ... -` 后收到空 stdin | 调用宿主与 PowerShell 管道组合不保留 stdin；不是 JSON/BOM 解析问题 | 所有编辑型 inspect 返回文件式 apply 契约，明确禁止 PowerShell here-string |
| 4 | `slide.number`、`slide.title` 被拒绝 | CLI 暴露字段组，Agent 按对象路径自然命名 | 已加入 identity/text 别名并覆盖真实组合测试 |
| 1 | `schema apply --op query` | 实验文本中的“查询”同时像动词和操作占位符；argparse 又在 JSON 协议外退出 | query/list/catalog 解释为操作目录；其他未知操作返回结构化 JSON |
| 2 | 漏传 `--allow-risk external_relationship` | inspect 只报告风险，没有把基础 argv、授权后 argv 和风险类型绑定返回 | 定向 inspect 返回 `apply_contract`，分别给出未授权与显式授权后的 argv |

## 系统性问题

1. **发现与执行割裂。** `patch_template` 原来只在 `--for edit` 返回，但真实任务使用 `content`、`layout` 和 `animation`，Agent 因此重新拼装 PatchRequest。
2. **协议并非全 JSON。** argparse 的 choices/缺参错误写入 stderr 并退出 2，Agent 收不到稳定的 `error_code`、`next_action` 和候选值。
3. **示例依赖 Shell 语义。** “支持 stdin”不等于所有 Agent 工具宿主都能可靠保留 stdin；Windows here-string 是已复现的不可靠组合。
4. **安全提示不够可执行。** 风险名称虽存在，但没有与当前文件路径、patch 文件和参数顺序组成机器动作。
5. **零错误不能只靠提示词。** 连续补充文字规则会增加上下文且仍可能被模型忽略；高频路径必须由返回协议直接携带。

## v0.2.2 行为

- `text-edit/content/edit/layout/animation` 五种定向 inspect 均返回 revision-bound `patch_template`。
- 同一响应返回 `apply_contract.argv_after_executable`、`risk_authorization_required` 和 `argv_after_explicit_risk_authorization`。
- `schema apply --op query|list|catalog|查询|列表` 成功返回紧凑操作目录，不产生重试。
- 拼错的真实操作名返回 `UNKNOWN_OPERATION`、最近候选和允许值。
- 所有 argparse 用法错误进入版本化 JSON envelope，不再泄漏纯 stderr usage。
- 没有放宽 revision、document_id、candidate、显式风险授权或原子写入规则。

## 离线验收门槛

- 完整 pytest 通过；原 argparse `xfail` 转为普通通过。
- EXE 对真实场景字段组合首次成功。
- EXE 对 `schema apply --op query` 返回成功目录。
- EXE 缺参返回 `INVALID_ARGUMENT` JSON。
- 含外部关系的 fixture 返回精确风险类型以及授权前后 argv。
- 不运行 API B-only；Token 与真实 Agent 零误调用仍留待有额度时验证。

## 本轮验证结果

- pytest：`114 passed`。
- EXE 版本：`0.2.2`。
- EXE SHA-256：`854669F2E1AED9BC33D22B2685A5B1A7B29EB7D60CDCDD2584F2D18A23E80195`。
- `schema apply --op query`：退出 0，返回 `operation_catalog`。
- `schema apply --op moev`：返回结构化 `UNKNOWN_OPERATION`，最近候选为 `move`。
- 缺少 inspect 文件参数：返回结构化 `INVALID_ARGUMENT`，不再输出 argparse 裸错误。
- 真实场景字段组合：首次成功；含外部关系 fixture 同时返回基础 apply argv、风险类型和显式授权后 argv。
- 定向 inspect 输出：`3,723 B`，低于 64 KB。

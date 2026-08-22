# 2026-08-22 验收进度与命令宿主事故记录

## 当前结论

已停止全部 A/B、WPS、清理和发布操作。原因不是产品测试失败，而是运行代理误用 PowerShell 保留变量 `$HOME`，导致对 `C:\Users\ASUS` 发起两次递归删除尝试。完整用户目录没有被删除，但无法排除部分文件已被删除。2026-08-22 13:21 的只读复核表明系统 `cmd.exe` 与 Windows PowerShell 已能启动；Codex 捆绑 PowerShell 的 `Modules` 目录确定缺失，因此该宿主的模块 cmdlet 仍不可用。

## 事故命令与影响边界

运行代理使用了：

```powershell
$home=Join-Path (Get-Location) 'results\local\token-api\_probe-home-test'
if(Test-Path -LiteralPath $home){Remove-Item -LiteralPath $home -Recurse -Force}
New-Item -ItemType Directory -Path $home
$env:CODEX_HOME=$home
...
Remove-Item -LiteralPath $home -Recurse -Force
```

PowerShell 变量名不区分大小写，且 `$HOME` 是只读自动变量。赋值失败后 `$home` 仍解析为 `C:\Users\ASUS`，所以两个 `Remove-Item` 都错误指向用户目录。

已知证据：

- 输出出现对 Codex runtime PowerShell、Node 等路径的 `Access denied` 和“目录不是空的”；
- 未发生完整删除 `C:\Users\ASUS`；
- 不能声称没有删除任何文件；
- 随后 PowerShell 内置模块加载失败；
- 事故发生后的首轮探针曾统一返回 `CreateProcessWithLogonW failed: 2`；
- 2026-08-22 13:21 复核时，系统 `cmd.exe` 与 Windows PowerShell 均可成功启动；
- `C:\Users\ASUS\.cache\codex-runtimes\codex-primary-runtime\dependencies\powershell\Modules` 确定不存在；
- `Desktop`、`Documents`、`Downloads`、`.codex` 均存在且非空，顶层条目数分别为 29、15、18、32；这些事实只能证明目录仍在，不能证明目录内没有零星文件损失；
- `.codex\config.toml` 存在（56 B），`.codex\auth.json` 不存在；未读取或输出任何凭据内容；
- A 基线清单和本事故记录仍存在。

## 本轮已完成的有效验收

### Luna Max/max A 基线

有效 run：`api-luna-max-a-v5-full`

- 6/6 场景 `returncode=0`；
- 6/6 含官方 `turn.completed` usage；
- 独立 Luna Max 原分辨率逐页视觉 QA：6/6 PASS；
- 输入 Token：5,139,601；
- 缓存输入：4,782,720；
- 未缓存输入：356,881；
- 输出 Token：80,629；
- 工具调用：108；
- 总耗时：2,046.054 秒；
- A 基线已冻结到 `acceptance/ab/api-token-a-baseline.json`；
- `--check-baseline` 已通过；
- A protocol hash：`3790d550001204e613d1f5f1e3f4de817889031dea812af1d42240e25d104b2c`。

场景 05 的 OOXML 证据为 3 个逐段效果加 1 个 fade，共 4 个动画节点；静态视觉通过。事故发生前尚未来得及对这份 A 输出做独立真实 WPS COM 重开，因此不能把 XML 证据表述成真实播放验收。

### 本地代码验证

- 产品全量 pytest 在本轮运行完成，退出码 0；
- A 运行环境探针：固定 `python-pptx` 与 skill `thumbnail.py` 均通过；
- B 隔离运行器定向测试：14 passed；
- 旧 `pptx` skill 已设计为按绝对路径 `skills.config enabled=false`；
- memory、plugins、skill_search、recommended_plugins 设计为 B 臂禁用。

## 无效运行

- `api-luna-max-a-v3-full`：猜测错误 Python 路径，无官方 usage；
- `api-luna-max-a-v4-full`：A 规则自身缺少路径引号，无官方 usage；
- `api-luna-max-b-v024-r1-20260822`：全局旧 skill 与 memory 自动注入，无官方 usage；
- `api-luna-max-b-v024-r2-isolated-20260822`：未进入场景、Token 0；
- `api-luna-max-b-v024-r3-isolated-20260822`：场景 01 在推理前退出，tool calls 0、turn.completed 0、Token 0。

这些运行不得用于 Token 降幅或质量结论。

## 尚未完成

- 没有有效 Luna Max/max B 结果；
- 尚不能计算新的 Luna A/B Token 降幅；
- A 场景 05 尚缺独立真实 WPS COM 结构证据；
- 六场景三轮 B 稳定性复测未开始；
- 3–5 份脱敏真实 PPT 试用仍缺；
- 根 LICENSE 仍需版权所有者选择；
- 复制目录仍未建立独立 Git commit/tag 来源链。

## 恢复后最短路径

1. 由用户或 Hermes 检查/恢复 `C:\Users\ASUS` 与 Codex runtime；不要由产品验收流程在当前损坏宿主上继续删除或安装。
2. `cmd.exe` 与 Windows PowerShell 已恢复启动；仍需恢复 Codex bundled PowerShell 的 `Modules` 目录，并验证其 cmdlet、Python 和 Codex CLI。
3. 对用户目录做文件完整性/备份检查，确认事故实际删除范围。
4. 重新运行 B 的离线 `debug prompt-input`，必须确认旧 `pptx` skill 和 memory 不在真实计费进程上下文。
5. 使用全新 run-id 运行一轮 B-only；失败则停，不追加两轮。
6. B 达标后再补两轮稳定性复测。

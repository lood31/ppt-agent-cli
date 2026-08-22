# Release checklist

任何一项标记为“阻断”的检查未完成时，不得创建公开 Beta 标签或发布包。

## 1. Legal and source freeze

- [ ] **阻断**：版权所有者选择项目根许可证，新增根 `LICENSE`，并在 `pyproject.toml` 中声明对应 license 元数据。
- [ ] **阻断**：复核 `THIRD_PARTY_NOTICES.md` 与本次 `uv.lock`、PyInstaller 分析结果一致，发行包带齐所需完整许可证文本。
- [ ] 检查密钥、真实/未脱敏 PPT、个人目录、`results/local/`、缓存和转储没有进入版本库或发行包。
- [ ] 独立 Git 工作树干净；发布 commit 可追溯，不把外层仓库提交误作本目录的发布提交。

## 2. Version and machine contracts

- [ ] 产品版本在 `pyproject.toml`、`src/ppt_agent/__init__.py`、EXE `--version` 和发布名称中一致。
- [ ] Schema 版本在 `src/ppt_agent/models.py`、capabilities、apply Schema 和冻结目录中一致。
- [ ] 重新导出 `capabilities.json` 与完整 `apply-schema.json`；不要复用旧版本冻结资产。
- [ ] 更新 `CHANGELOG.md`，将 `Unreleased` 内容归入最终版本与日期。

## 3. Reproducible build

```powershell
uv lock --check
uv sync --frozen --all-groups
.venv\Scripts\python.exe -m pytest -q --basetemp .tmp-release-tests
powershell -ExecutionPolicy Bypass -File tools\build_exe.ps1
.venv\Scripts\python.exe tools\create_freeze.py
.venv\Scripts\python.exe tools\create_release_zip.py --require-root-license
```

- [ ] `uv.lock` 与 `pyproject.toml` 同步。
- [ ] 全量测试通过，`git diff --check` 通过，临时测试目录已清理。
- [ ] 在干净目录中只复制 EXE，依次运行 `--version`、`capabilities`、`schema apply --op set_text` 和 `doctor`。
- [ ] **阻断**：目标 Windows/WPS 机器上的 `doctor` 明确确认 WPS COM 与 render 所需 `pdftoppm` 可用；失败时返回可操作的结构化原因。

## 4. Product acceptance

- [ ] 六场景 B-only 质量 6/6、错误 CLI 调用 0、安全/误改事故 0、单次文本输出小于 64 KB。
- [ ] 三轮质量通过率 100%；平均与中位 Token 降幅至少 70%；任何单轮不低于 65%。
- [ ] 真实 WPS 证据分别覆盖动画效果数、切换、回开、render、review token、accept、baseline 与 WAL 收敛；原件哈希保持不变。
- [ ] **阻断**：完成 3–5 份脱敏真实 PPT 的完整试用，覆盖普通演讲、课程作业、现有模板/图表、人工修改后 diff、动画/备注/切换，并记录人工返工次数。
- [ ] WAL 损坏、超时、保存失败、弹窗/残留进程、revision 冲突、重复 request、accept/discard 和事务回滚测试通过。

## 5. Read consistency decision

- [ ] `render` 与 `qa --suggest-fixes` 的结果绑定一致 revision；并发修改只能导致明确冲突，不能让旧预览令牌确认新内容。
- [ ] 纯 `inspect`、`diff`、`qa` 若继续采用乐观读，在 README/设计中明确并发语义；全局共享读锁不是 Beta 的默认阻断项。

## 6. Install and uninstall smoke

```powershell
powershell -ExecutionPolicy Bypass -File tools\install.ps1
ppt-agent --version
powershell -ExecutionPolicy Bypass -File tools\uninstall.ps1
```

- [ ] 普通用户权限安装成功，新的终端能从用户 PATH 调用。
- [ ] 卸载只删除精确安装文件；默认保留运行状态，`-RemoveState` 仅在用户明确选择时删除状态目录。
- [ ] 安装后从一份脱敏 PPT 走通 inspect → apply → render → accept。

## 7. Release artifact and publication

- [ ] 重新生成冻结 manifest；逐文件校验源码、Schema、capabilities 和 EXE 哈希。
- [ ] 发行 ZIP 包含 EXE、README、CHANGELOG、根 LICENSE、`THIRD_PARTY_NOTICES.md`、`vendor/hands_on_deck/LICENSE`、`vendor/hands_on_deck/NOTICE.md`、由 `create_release_zip.py` 收集的当前 runtime/build closure 完整许可证文本、安装与卸载脚本；ZIP 旁提供 `SHA256SUMS`。收集器遇到缺失或空许可证文本时必须 fail-closed。
- [ ] 在另一目录解压并核对 SHA-256，执行最终 smoke。
- [ ] 创建最终 Git commit 和带注释标签；标签指向已验证 commit。
- [ ] 发布说明明确支持边界、WPS/Windows 要求、回退旧 `pptx` skill 需用户同意，以及已知 P2。

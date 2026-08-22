# hands-on-deck 安全与行为审计

## 固定版本

- 来源：https://github.com/EveryInc/hands-on-deck
- Commit：`a24b996ecff6393ccf39c4fee2b88c493fb0b693`
- 许可证：MIT
- 审计日期：2026-08-12
- 审计范围：仓库 45 个文件；重点逐行检查 7 个 Python 脚本、测试、Skill 与 CI。

## 结论

风险等级：中低。可作为固定版本、离线运行的普通 PPTX 编辑引擎。

未发现遥测、HTTP 客户端、凭据访问、浏览器会话访问、`eval`/`exec`、混淆代码、提权或系统配置修改。核心脚本只读写显式传入的 PPTX、patch、图片和输出目录。

## 权限与子进程

- 文件读取：显式传入的 PPTX、patch JSON、本地图片。
- 文件写入：显式输出 PPTX、渲染目录和系统临时目录。
- 子进程：`soffice` 与 `pdftoppm`，参数使用列表传递，未启用 shell。
- 网络：核心 Python 路径无网络调用。HTML 转 patch 对远程图片明确跳过。
- 可选依赖：`html2patch.py` 需要 Playwright/Chromium，本产品 MVP 不启用该路径。

## 发现与处置

- 上游公开 `xml set`：与产品安全模型冲突；`ppt-agent` 不暴露该入口。
- 上游渲染使用 LibreOffice：与 WPS-first 验收标准冲突；产品只复用 inspect/patch/diff，正式 render 改用 WPS COM。
- 上游无法创建对象动画和原生图表：由 WPS COM 事务尾部补齐。
- `html2patch.py` 可解码本地 `data:` 图片：用途明确且未用于产品核心路径。
- `merge_decks.py` 与旧 `replace.py` 会清理自己的临时文件：目标由内部临时路径产生，未纳入 vendored 最小集合。

## 供应链固定

本项目只 vendoring `deck.py`、`inventory.py`、`replace.py` 与 MIT LICENSE。文件哈希见 `vendor/hands_on_deck/NOTICE.md`。运行时不自动更新、不联网、不安装依赖。

## 验证

- 上游核心测试：40 通过，1 失败。
- 唯一失败：上游 `render` 测试在当前 Windows 环境调用 LibreOffice 未产生 PDF。
- 产品 WPS render、PDF 转 JPEG、动画与图表链路均独立通过。

# OfficeCLI 安全与行为审计

## 固定版本

- 来源：https://github.com/iOfficeAI/OfficeCLI
- Commit：`459b1a473faf33f2f52e697ac6d265a3f67b176a`
- Release：`v1.0.143`
- Windows x64 SHA-256：`d4d4c10fced307e209744cf98a56b003a6e613424fd651b08469274704afd2c6`
- 许可证：Apache-2.0；依赖 `DocumentFormat.OpenXml 3.4.1`、`System.CommandLine 3.0.0-preview.2.26159.112`、.NET Runtime 均为 MIT。
- 审计日期：2026-08-12
- 审计范围：固定 commit 的 638 个核心源码、Schema、安装脚本与许可证文件。

## 结论

风险等级：中高。功能覆盖强，但默认运行行为不满足本产品“固定版本、离线、无自动更新、无外部素材下载”的安全门槛，未选为 MVP 内部引擎。

## 阻断项

1. `AutoUpdate` 默认值为 `true`，普通命令会触发后台版本检查并可能下载替换二进制。
2. 每次版本变化会刷新已安装到 Agent 目录的技能文件。
3. 裸命令存在首次自动安装逻辑，可能复制二进制并安装技能/MCP。
4. 图片和通用文件源支持 HTTP(S) URL；虽然实现了 SSRF 防护和 50 MB 限制，仍与 MVP 只接受本地素材冲突。
5. 更新请求的 User-Agent 携带版本，服务端访问日志可形成版本分布统计；源码明确称其为 telemetry。
6. 安装命令会扫描并写入多种 Agent 配置目录和 MCP 配置。

## 正向发现

- 更新资产使用版本固定 URL并校验 SHA-256；缺失或不匹配会拒绝。
- 远程素材实现 DNS/连接阶段 SSRF 防护、重定向检查和大小限制。
- 无 `eval`/动态执行外部代码；子进程参数使用结构化传递。
- Schema 丰富，原生图表与动画 OOXML 能力值得后续在严格离线封装后复评。

## PoC 处置

没有运行 `install.ps1`、`install.sh`、`officecli install` 或 MCP/技能安装。官方二进制下载因网络中断未完成，因此没有把静态审计误写成已运行验证。若未来复评，必须同时设置 `OFFICECLI_NO_AUTO_INSTALL=1`、`OFFICECLI_SKIP_UPDATE=1`，先将 `autoUpdate` 配置为 false，并禁止 URL 素材。

# 真实 PPT 一周试用记录

真实文件仅放在 `fixtures/private/` 或仓库外，不提交 Git。每份文件先脱敏并记录初始 SHA-256。

| 日期 | 文件代号 | 类型 | 页数 | 任务 | CLI 调用 | 是否回退原 skill | 错误/误报 | 遗漏/误改 | 人工返工 | WPS 打开/播放 | 证据路径 |
|---|---|---|---:|---|---:|---|---|---|---:|---|---|
| 2026-08-13 | grade9-beishi-ch4-similarity | 授课 | 10 | 九年级北师大版上册第四章《图形的相似》真实试讲版 | `inspect` / `qa basic,presentation` / LibreOffice render / `apply add_animation` 探针 | 否；静态创建后用本地渲染验证 | WPS COM `WPS_COM_FAILED`：无效的类字符串；静态 QA 无错误 | 首轮第 09 页侧栏高亮错误，已修复；WPS 动画未写入 | 1 次（导航高亮与关键标注可读性） | 未验证；WPS `doctor` 为 `wps_com=false` | `results/local/trials/2026-08-13-grade9-beishi-ch4-similarity/` |
| 2026-08-23 | math-projection-view-01 | 授课 | 12 | 《投影与视图》真实课件；将残留的“题”改为“课堂练习”，增加备注、逐段淡入动画与 wipe 切换 | `inspect` / `qa` / `apply` / `diff` / `render` / `accept` / WPS 回开 | 否 | 首次 `replace_text` 因文字跨 run 被 fail-closed 拒绝，改用精确 `set_text`；调用错误 1 次、数据事故 0 | 原稿已有 11 条布局 warning；候选未增加 warning，第 7 页文字无溢出，第 8/11 页渲染哈希与基线一致 | 0 次 | WPS 12.0 回开、PDF/JPEG render 通过；第 8 页动画序列 3 项，wipe=`2820`；accept 后 WAL=0、WPS 残留进程=0 | `results/local/beta-release-v024b1-final-20260823/real-trial-math/`；原件 SHA-256 `1b8b1ebd34b0a1f180191205540a6fd06ef2e982d1e30da7ca558a5eb5dffe18` |
| 2026-08-23 | mixed-science-review-01 | 授课/复杂模板 | 26 | 九上电流与电路复习课件；修改首页副标题、备注，增加淡入动画与 wipe 切换 | `inspect` / `qa` / `apply` / `diff` / `render` / `accept` / WPS 回开 | 否 | 数据事故 0；原稿已有 31 条 basic 布局 warning，候选未增加 warning | 第 1–11 页为物理、第 12–26 页转为化学，属于原素材内容混杂；第 11 页原题图偏糊；候选无额外视觉破坏 | 0 次 | WPS 12.0 回开、PDF/JPEG render 通过；首屏动画 1 项，wipe=`2820`；accept 后 WAL=0、WPS 残留进程=0 | `results/local/beta-release-v024b1-final-20260823/real-trial-mixed-science/`；原件 SHA-256 `2e4da7cea993dd2e9cf26d59fd7564a7d0d7d0421bf42dcdb84f319143c27607` |
| 2026-08-23 | qa-chart-workflow-01 | 演讲/图表/规范 | 18 | QA 验收流程规范新版；与 16 页旧版做 diff，修改首页副标题、备注和原生图表标题，增加动画与切换 | `inspect` / `diff` / `qa` / `apply` / `render` / `accept` / WPS 回开 | 否 | 数据事故 0；原稿已有 15 条 basic 布局 warning，候选未增加 warning | 两个原生图表均保留；第 9 页较长的新标题自动换为两行且“验收”拆行，为非阻断美观项 | 0 次 | WPS 12.0 回开、PDF/JPEG render 通过；图表标题为“2024区域营收与同比增长（验收）”，首屏动画 1 项，wipe=`2820`；accept 后 WAL=0、WPS 残留进程=0 | `results/local/beta-release-v024b1-final-20260823/real-trial-qa-chart/`；新版原件 SHA-256 `ace06a24862f049d39d32dd2c53f71c5b5aa158a1baa7859f4c43552bde8cb4c`；旧版 SHA-256 `0dacd242d1c086a8fe47511dceb4734e495dae937f456472f1d72e931e4c150e` |

记录原则：

- 每行状态只描述该次试用当时的环境与结果；后续 WPS 可用性或修复不会追溯改写历史记录。
- 每次 CLI 不够用、误报、内容丢失、需要回退原 skill 或需要手工恢复，都记录为失败案例。
- 同一缺口至少重复出现两次，才进入 v0.2 候选；安全或数据损坏类问题出现一次即阻断。
- 一周结束只按证据排序，不依据功能想象扩展范围。

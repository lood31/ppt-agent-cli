# 真实 PPT 一周试用记录

真实文件仅放在 `fixtures/private/` 或仓库外，不提交 Git。每份文件先脱敏并记录初始 SHA-256。

| 日期 | 文件代号 | 类型 | 页数 | 任务 | CLI 调用 | 是否回退原 skill | 错误/误报 | 遗漏/误改 | 人工返工 | WPS 打开/播放 | 证据路径 |
|---|---|---|---:|---|---:|---|---|---|---:|---|---|
| 2026-08-13 | grade9-beishi-ch4-similarity | 授课 | 10 | 九年级北师大版上册第四章《图形的相似》真实试讲版 | `inspect` / `qa basic,presentation` / LibreOffice render / `apply add_animation` 探针 | 否；静态创建后用本地渲染验证 | WPS COM `WPS_COM_FAILED`：无效的类字符串；静态 QA 无错误 | 首轮第 09 页侧栏高亮错误，已修复；WPS 动画未写入 | 1 次（导航高亮与关键标注可读性） | 未验证；WPS `doctor` 为 `wps_com=false` | `results/local/trials/2026-08-13-grade9-beishi-ch4-similarity/` |
|  |  | 演讲/作业/模板 |  |  |  |  |  |  |  |  | `results/local/trials/...` |

记录原则：

- 每行状态只描述该次试用当时的环境与结果；后续 WPS 可用性或修复不会追溯改写历史记录。
- 每次 CLI 不够用、误报、内容丢失、需要回退原 skill 或需要手工恢复，都记录为失败案例。
- 同一缺口至少重复出现两次，才进入 v0.2 候选；安全或数据损坏类问题出现一次即阻断。
- 一周结束只按证据排序，不依据功能想象扩展范围。

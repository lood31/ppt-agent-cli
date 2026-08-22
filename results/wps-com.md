# WPS COM PoC 结果

日期：2026-08-12
环境：Windows，WPS Office 安装目录版本 `12.1.0.26895`，COM `app.Version` 返回 `12.0`，ProgID `KWPP.Application`。

## 结论

硬门槛通过。使用独立、不可见 WPS 实例在合成副本上完成：

- 枚举 4 页和目标 shapes；
- 修改文本；
- 添加 `fade` 对象动画；
- 设置 `fade` 页面切换；
- 修改原生柱状图标题；
- 保存、关闭并只读重开；
- 重开后动画计数为 1，EffectType 为 10；
- 重开后切换 EntryEffect 为 3849；
- PDF 导出成功；
- 实例正常退出。

产品 E2E 又在已有 1 个动画的测试稿上追加动画；重开后的第 1 页动画计数为 2，证明普通 patch 与 WPS 动画写入没有清除原动画。

原始临时证据已汇总为 `results/wps-com.json`，终检后清理，不作为发布资产提交。

# 高风险测试补强与缺陷回归

日期：2026-08-13

## 结果

- 37 passed，1 strict xfail。
- 总覆盖率：74%（冻结基线为 52%）。
- `cli.py`：92%（冻结基线为 0%）。
- `state.py`：89%。
- `wps.py`：56%（冻结基线为 15%）。

没有机械追求 90% 总覆盖率；测试集中覆盖用户入口、状态机、WPS 事务边界及本轮验收缺陷。

## 已覆盖风险

- 12 个冻结命令的参数解析与 dispatch。
- CLI 成功和领域错误的 JSON 输出与退出码。
- revision 冲突、同一 `request_id` 不同载荷冲突。
- review token 拒绝、accept 提升、discard 删除。
- WPS 动画/保存失败时不发布 candidate，原件不变，请求不落幂等记录。
- WPS 异常时关闭 presentation，并只退出自己创建的 COM 实例。
- quote 多正文保留、`swap_image` 发布、逐段动画参数传递。
- `diff` 前后方向和局部 render 旧图片清理。

## 仍保留的 strict xfail

1. argparse 用法错误仍绕过统一 JSON 错误信封并退出 2。

## 尚未自动化

- WPS COM 超时与强制中止策略：产品当前没有超时封装，无法只靠测试补齐。
- 真实模态弹窗检测：需要专门实机夹具或 UI 自动化。
- WPS 图表写入失败后的真实 COM 回滚：当前仅有事务层故障注入测试。

# SL651-Toolkit v1.5.1 自审计报告

> 日期：2026-11-22
> 角色：修复方自审计（只审不修本轮之外的既有代码；本轮发现的问题已修）
> 基线：v1.5.1（v1.5.0 + v3.1 的 L-1/I-A~I-F 修复）
> 方法：全套件回归 + 真实语料 + 常量表程序化对照 + 定向变异 + 文档/版本扫描 + diff 精读
> 结论：**未发现新的 Medium/High；自审计期间发现并修复 6 处 Info/边界问题，另补 2 处文档/注释（SA-1~SA-7）。** 12/12 套件通过。

---

## 一、自审计发现并修复

| # | 位置 | 问题 | 处理 |
|---|------|------|------|
| SA-1 | `sl651/decoder.py::_parse_downlink_body`（0x49） | 非标定义符降级后 `pos` 未推进，会额外报“正文长度不是 8B 整数倍”，双重告警 | 降级时把 `pos` 置到末尾，仅保留定义符告警 |
| SA-2 | `sl427/decoder.py::_parse_parameter_records`（B1 0x0A） | `remaining==5`（5B 位图、无值）未识别为位图，会被当作单参数 4B 值误读 | 位图判定增加 `remaining==5` 分支；无值时由位图解析器告警 + 调用方降级原始摘要 |
| SA-3 | `sl651/decoder.py::_parse_downlink_body`（0x3A/0x40/0x42） | 尾部不足 4B/标识符不完整时静默忽略，违背“降级留痕”原则 | 增加 3A/40H 尾部 warning |
| SA-4 | `sl651/encoder.py::build_set_param_body` docstring | 未提示“密码等表D HEX 参数不能走 BCD 通用方法” | 补 docstring，指向 `build_change_password_frame` |
| SA-5 | 文档/版本 | v1.5.1 已改代码，但 `audit_index`/`project.md` 测试描述仍只写 v1.5.0 | 已同步到 v1.5.1；`audit_index` 加 v3.1 |
| SA-6 | `sl427/decoder.py::_parse_water_quality_427` | 59H/5AH 数据 <5B 时 `consumed=0`，原条件 `consumed and ...` 不告警，静默空结果 | 条件改为 `data and consumed < len(data)`，短数据留 warning |
| SA-7 | `sl427/decoder.py::_parse_query_response`（5DH） | 64B 中 ERC19~32 为备用，原 `_warn_tail` 把尾部 28B 报成“未展开” | 移除 5DH 的尾部 `_warn_tail`；保留 64B 固定长度检查 |

---

## 二、程序化对照结果（无新差异）

| 表 | 对照方式 | 结果 |
|----|----------|------|
| SL651 表C.1 → `SL651_ELEMENT_DEFS` | 从规约 txt 逐行提取 N(D,d)/固定字节，按注 g/F4/F5~FC 修正后比对 | 127/127 一致，无缺失/多余 |
| SL651 表D.4 → `SL651_PARAM_DEFS_D4` | 逐行提取 135 行 N(D,d) 比对 | 135/135 一致；另手工补 97/98=(0,0) |
| SL651 表D.1 → `SL651_PARAM_DEFS_D1` | 固定长度行比对 | 01/02/03/0C/0D 一致（0D=8B，表D.2 A1~A8） |
| SL651 表D.2 → `SL651_PARAM_NAMES` | 名称/引导符扫描 | 142 项无空名/页眉/行号污染 |
| SL427 表18 → `WATER_QUALITY_SPECS` | 31 行可解析 N(D,d) 比对 | 名称/单位/小数位全部一致 |
| SL427 表33~44 → `CTRL_FUNC_MAP` | 既有 v3.1 已逐项核对；本轮复跑关键类型 | 一致，`COMP_BITS` 未动 |

---

## 三、回归与健壮性

```text
python3 -B tests/run_all.py            → 12/12
python3 -m compileall -q ...           → OK
git diff --check                       → 0
福建 23 / 北京 25 条 CLI 回放           → 0 失败
SL427 随机 2 万帧 + SL651 随机 2 万帧   → 0 未受控异常
```

定向用例：

- 41H `0x0D` → `0D40`；41H 参数名 → 中心站地址(4B) 等；
- 43H `0x97/0x98` → `9700/9800`，名称/定义符正确；
- 49H 非标 `03 11` → 原始摘要 + 单条 warning；
- FD `FD FD` → 固定标志兼容 + warning；F3/FD 载荷完整；
- B1 0x0A 4B / 5B 位图 + 4B / 5B 位图无值 → 分别正确/告警/降级；
- 综合参数 0x03/0x0A/0x0B 块 → 正确；0x0A 仅 4B → 原始摘要 + warning。

---

## 四、仍无法自证的项（非代码遗漏）

1. **41H 04~0B/0E/0F**：规约本身“不定长”，无法自动推导定义符；需 `(guide,len,dec)`。
2. **83H/61H 图片 `L×1K`**：无已确认样本；继续保守降级。
3. **05H 时段长 HH.mm**：按 2B/0 收录，非 `N(D,d)`，需现场确认。
4. **综合参数水质块参数种类**：已做“严格位图优先 + 4B 原始降级”的可观测兼容；具体参数语义需真实 RTU 样本。
5. **现场回放**：0x07/0x09/0x0A/0x0F、B1 0x0A 双形态仍需真实帧最终裁决。

---

## 五、自审计结论

- v1.5.1 的代码/测试/文档在当前工作区自洽；自审计未发现新的数据正确性或互通性缺陷。
- 上述 SA-1~SA-5 均为边界/告警/文档级，不影响既有闭环结论。
- 建议下一轮把 83H/61H 的 `L×1K` 与 41H 变长参数作为独立需求（需样本/现场），不再作为“修复遗漏”处理。

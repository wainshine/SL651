# SL651-Toolkit v1.5.1 修复报告

> 日期：2026-11-22
> 基线：v1.5.0（修复 v3.0 全部发现）
> 依据：`audit/audit_report_v3.1.md`
> 测试：`python3 -B tests/run_all.py` → **12/12**
> 提交状态：按用户要求 **未执行 git add/commit**
> 自审计：`audit/self_audit_v1.5.1.md`（未发现新 Medium/High；补 4 处边界/告警与 2 处文档）

---

## 一、闭环清单

| 编号 | 级别 | 修复 | 位置 |
|------|------|------|------|
| L-1 | Low | `SL651_PARAM_DEFS_D1["0d"]` 由 `(4,0)` 改为 `(8,0)`：表D.2 采集要素位图为 A1~A8 共 8 字节；41H 读取该参数由 `0D20` 改为 `0D40` | `sl651/constants.py`；`tests/test_spec_conformance.py` 断言 `0D40` |
| I-A | Info | 增加 `SL651_PARAM_NAMES`（表D.1/D.4 名称），41H/43H 下行显示“中心站地址(4B)/定时报时间间隔(1B)”等语义名 | `sl651/constants.py`、`sl651/decoder.py::_parse_downlink_body` |
| I-B | Info | 49H 下行/上行密码解析校验 `03 10H`，非标定义符降级原始摘要 + warning，不再按固定步长盲切 | `sl651/decoder.py` |
| I-C | Info | FD 的 `FD FD` 兼容口径显式写 warning（规约注 f 固定 F6H），不再静默接受 | `sl651/decoder.py` F3/FD 分支 |
| I-D | Info | 去掉 `_parse_elements` 中两分支同为 `break` 的死条件 | `sl651/decoder.py` |
| I-E | Info | 综合参数水质块优先按“5B 位图 + N×4B”严格口径；若仅剩 4B（缺少位图），降级为“水质(原始4B)”+ warning，不猜参数种类 | `sl427/decoder.py::_parse_comprehensive` |
| 补 | — | 下行 40H/42H 数据短于声明长度、3AH 标识符/40H 尾部不足、49H 正文非 8B 整数倍时写 warning；B1 0x0A 的 5B 位图（无值）按位图告警而非单值误读；59H/5AH 短数据告警；5DH 备用区不再误报“未展开” | `sl651/decoder.py::_parse_downlink_body`、`sl427/decoder.py` |
| I-F | Info | 测试 docstring 由“16 个类型码”改为“13 个标量/结构类型码（0x00/0x0D/0x0E 上下文相关除外）” | `tests/test_spec_conformance.py` |

---

## 二、验证

```text
python3 -B tests/run_all.py  →  12/12 套件全部通过
python3 -m compileall -q ...  →  OK
git diff --check              →  0
```

新增/更新断言：

- `build_read_config_frame([0x0D])` → `0D40`；
- 41H 下行首参数名 → `中心站地址(4B)`；
- 49H 正常帧仍解出旧/新密码；非标 `03 11` 帧降级原始摘要 + warning；
- FD F6 正常帧不受影响；FD FD 兼容帧带 warning；
- 40H 短数据/49H 尾随、综合参数水质 4B 降级均有 warning；
- 规约符合性套件 12 组全通过。

---

## 三、行为变化

- 仅 41H 的 `0x0D` 参数定义符由 `0x20` 变 `0x40`（修复）；其余线格式不变。
- 下行 41H/43H 的参数 `name` 变为语义名称（纯展示）。
- 非标 49H/FD 帧新增 warning（值可能降级为原始摘要），不影响合规帧。

## 四、遗留

- I-E：已实现“严格位图优先 + 4B 原始摘要降级”的可观测兼容；具体参数语义仍需真实 RTU 综合参数样本裁决。
- 83H/61H 图片 `L×1K` 分帧仍未重组（无确认样本）。

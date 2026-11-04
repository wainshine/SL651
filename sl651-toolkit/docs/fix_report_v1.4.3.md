# SL651-Toolkit v1.4.3 修复报告

> 日期：2026-11-05  
> 基线：v1.4.2（`fcdeb9f`）  
> 版本：v1.4.3  
> 依据：`audit/audit_report_v2.8.md` + `audit/audit_review_v2.8.md`  
> 测试：`python3 -B tests/run_all.py` → **11/11**

---

## 一、闭环项

| 编号 | 修复 | 关键位置 |
|---|---|---|
| M-1 | ASCII 标识符单点大小写无关 lookup（casefold）；`pH/PH/ph` 均命中；`ElementValue.code` 保留 `pH` 原始大小写；多值收集同源 | `sl651/decoder.py` |
| M-2 | SL427 数据域统一受保护入口；DIV 重组非法 BCD 降级原始摘要 + warning，不再裸抛 `ValueError` | `sl427/decoder.py` |
| L-1 | B1 多记录按 `func_code` 逐条展开；尾随不足一条时输出“剩余 N B 未展开”warning | `sl427/decoder.py` B1 分支 |
| L-2 | B1 起止时间做时/月/日 + 真实日历校验（含 2 月 31 日），越界显示 `-` + warning | `sl427/decoder.py` B1 分支 |
| L-3 | fixture 测试 docstring 改为“工具显示口径基线”（映射/单位经 PDF 核对） | `tests/test_constants_spec.py` |

---

## 二、验证

```text
python3 -B tests/run_all.py → 11/11
```

新增/扩展覆盖：

- `test_constants_spec.py`：每个 ASCII 表键必须被 `_lookup_ascii()` 命中（含 pH/PH/ph）；
- `test_protocol_contracts.py`：`build_ascii_frame([("pH","7.2")])` 运行时解码出名称 `pH`、code `pH`；
- `test_sl427_multiframe.py`：DIV 重组非法 BCD 降级原始摘要；B1 12 条记录展开/尾随半条/时间越界；
- `test_fuzz_decoders.py`：新增 SL427 DIV feed 变异 120 组，无未受控异常。

测试组数：变异 5 组、SL427 分帧 15 组、协议契约 15 组、表 C.1/G.1 常量 6 组。

---

## 三、说明

- M-2 的正常 `decode()` 路径仍对数据域非法值抛受控 `DecodeError`；仅 DIV 重组 `degrade=True` 时降级原始摘要 + warning，不改变单帧契约。
- L-1 对非数组 func 逐条切片解析，对数组型 func 使用现有 parser；只有尾随不足一条时才 warning。
- 本轮未执行 `git add/commit`。

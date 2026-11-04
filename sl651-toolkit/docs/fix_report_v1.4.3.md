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
| M-1 | ASCII 标识符单点大小写无关 lookup（casefold）；`pH/PH/ph` 均命中；多值收集同源 | `sl651/decoder.py` |
| M-2 | SL427 数据域统一受保护入口；DIV 重组非法 BCD 降级原始摘要 + warning，不再裸抛 `ValueError` | `sl427/decoder.py` |
| L-1 | B1 多记录单条解析时输出“仅解析首条/剩余未展开”warning | `sl427/decoder.py` B1 分支 |
| L-2 | B1 起止时间做日历范围校验，越界显示 `-` + warning | `sl427/decoder.py` B1 分支 |
| L-3 | fixture 测试 docstring 改为“工具显示口径基线”（映射/单位经 PDF 核对） | `tests/test_constants_spec.py` |

---

## 二、验证

```text
python3 -B tests/run_all.py → 11/11
```

新增/扩展覆盖：

- `test_constants_spec.py`：每个 ASCII 表键必须被 `_lookup_ascii()` 命中（含 pH/PH/ph）；
- `test_protocol_contracts.py`：`build_ascii_frame([("pH","7.2")])` 运行时解码出名称 `pH`；
- `test_sl427_multiframe.py`：DIV 重组非法 BCD 降级原始摘要；B1 多记录/时间越界；
- `test_fuzz_decoders.py`：新增 SL427 DIV feed 变异 120 组，无未受控异常。

测试组数：变异 5 组、SL427 分帧 15 组、协议契约 15 组、表 C.1/G.1 常量 6 组。

---

## 三、说明

- M-2 的正常 `decode()` 路径仍对数据域非法值抛受控 `DecodeError`；仅 DIV 重组 `degrade=True` 时降级原始摘要 + warning，不改变单帧契约。
- L-1 的 warning 只在 `func_code` 定义非数组且 `rest` 超过单条长度时触发；数组型 func 由现有 parser 逐条处理。
- 本轮未执行 `git add/commit`。

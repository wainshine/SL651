# SL651-Toolkit v1.4.2 修复报告

> 日期：2026-11-03  
> 基线：v1.4.1，git `44535d6`  
> 版本：v1.4.2  
> 依据：`audit/audit_report_v2.7.md` + `audit/audit_review_v2.7.md` + `docs/fix_plan_v1.4.2.md`  
> 测试：`python3 -B tests/run_all.py` → **11/11**

---

## 一、闭环项

| 编号 | 修复 | 关键位置 |
|---|---|---|
| M-1 | 表 C.1 全量补齐；ASCII 130 字面键；表 G.1 独立 | `sl651/constants.py`、`tests/test_constants_spec.py` |
| M-2c | 上行 SYN 16 位长度；下行 SYN 12 位；legacy 12 位 | `sl651/decoder.py` `_extract_frame/_handle_syn/_find_valid_start/_decode_binary` |
| M-2a | 重组结果直接解析，取消 4095 合成帧上限 | `sl651/decoder.py` `_decode_reassembled` |
| M-2b | SL427 DIV 直接解析，取消 255 合成帧上限 | `sl427/decoder.py` `_decode_div_reassembled` |
| L-1 | ASCII 分类码用 ASCII 字符，兼容 2 字符 HEX | `sl651/encoder.py`、`sl651/decoder.py` |
| L-2 | ASCII SYN 包号按 HEX | `sl651/decoder.py` `_handle_syn` |
| L-3 | `decode()` SYN 分包安全降级（空要素 + warning） | `sl651/decoder.py` |
| L-4 | 0x26 N(6,1) 文档/注释 | `simulator/*`、README/handoff |
| L-5 | YAML center/password 类型/范围校验 | `tools/simulate_cli.py` |
| L-6 | AFN=B1 固态存储头/数据解析 | `sl427/decoder.py` |
| L-7 | AFN=84 超长 warning | `sl427/decoder.py` |

---

## 二、关键行为

### 2.1 SL651 大正文

- 单包 5003B（3B 包头 + 5000B 正文，表22 16 位长度）：`feed()`/`decode()` 均可解析；
- 两包合计 5050B：`feed()` 重组成功，不再报 `重组正文超范围(>4095)`；
- `decode()` 对 `total>1` 的 SYN 分包：`elements=[]`，warning 提示使用 `feed()`；
- 逐包 CRC、乱序、缓存上限、重同步测试保持通过。

### 2.2 SL427 大正文

- 300B D 分片（两片 150B）：`feed()` 直接解析，不再报 `重组用户区超范围(L≤255)`；
- B1：前 9B 表48 头（参数种类/编号 + 起止时间），后续按 `ctrl["func_code"]` 分派 7.3.22；
- 84：D>2B 时输出 warning，仍解析前 2B。

### 2.3 表基线

- `SL651_ELEMENTS`：132 键（表 C.1 131 行 + 80H 自定义）；
- `SL651_ASCII_ELEMENTS`：130 字面键；`DRxnn` 动态识别；
- `SL651_ASCII_ELEMENTS_G`：表 G.1 独立核心表（12 码），不与 C.1 混用；
- 新增 `tests/test_constants_spec.py`，套件 10 → 11。

---

## 三、验证

```text
python3 -B tests/run_all.py
  主测试套件 / 盲区 / 模拟器集成 / 变异 / SL427 参数、查询、控制
  / SL651 多包 12 组 / SL427 分帧 14 组 / 协议契约 14 组 / 表 C.1/G.1 4 组
  → 11/11
```

另手工验证：

- 5003B 单包、5050B 双包：`feed()` 成功；
- 300B SL427 双片：`feed()` 成功；
- `decode()` SYN 分包：空要素 + warning；
- `center: "2"` / `password: "0"`：可读配置错误，不裸栈；
- B1、84 超长：测试覆盖。

---

## 四、残余

- 表 G.1 当前只落核心 12 码；完整 142 行随 0x35 人工置数解析补齐。
- 83/61 图片 `L×1K` 仍按 v1.4.1 保守降级（SA-R3 待真实样本）。
- SL427 B1 后续数据按 `func_code` 标量解析；多记录数组的完整展开可后续增强。
- 未执行 `git add/commit`；提交由用户完成。

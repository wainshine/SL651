# v1.4.3 自审计报告

> 日期：2026-11-05  
> 基线：v1.4.3（git `8d920ad`）  
> 范围：v2.8 M-1/M-2/L-1/L-2/L-3 修复  
> 方法：diff 精读 + 构造回放 + 全量套件 + 针对性边界  
> 结论：**未发现新的 Medium/Critical；发现并修复 1 个 Low（ASCII pH 的代码字段仍被大写）**，当前 `run_all.py` 11/11。

---

## 一、发现并修复

### SA-1（Low）：`pH` 的名称/单位已修复，但 `ElementValue.code` 仍被 `upper()`

**位置**：`sl651/decoder.py::_parse_ascii_elements` 的 `ElementValue(code=code.upper(), ...)`。

**问题**：M-1 修复后 lookup 已能命中 `pH`，但输出要素的 `code` 仍是 `PH`：

```text
build_ascii_frame([("pH","7.2")]) → [("PH", "pH", 7.2, "")]
```

名称/单位已正确，但协议标识符本身是大小写敏感的 `pH`；依赖 `code` 做二次匹配的调用方仍会看到不一致的 `PH`。这不是数据错误，属于元数据一致性 Low。

**修复**：ASCII 路径改为保留原始 `code`（`code=code`），HEX/BCD 路径不变。  
**测试**：`test_protocol_contracts.py` 断言 `e.code == "pH"`；全表 lookup 不变量保持通过。

---

## 二、复核通过项

| 项 | 结果 |
|---|---|
| M-1 casefold lookup | `pH/PH/ph` 全部命中；130 个表键不变量通过 |
| M-1 多值收集 | `nxt_entry` 使用同一 `_lookup_ascii` |
| M-2 受保护入口 | 正常 `decode()` 仍抛受控 `DecodeError`；DIV `degrade=True` 降级原始摘要 + warning |
| M-2 fuzz | 120 组 DIV 变异无未受控异常 |
| L-1 B1 多记录 | 12×3B 记录逐条展开；尾随半条输出「剩余 1B 未展开」warning |
| L-2 B1 时间 | 时=30/月=23 显示 `-` + warning，不再显示 `30:00` |
| L-3 docstring | 已改为「工具显示口径基线」 |
| 版本/计数 | v1.4.3；11 套件；测试组数文档一致 |

---

## 三、残余

1. **表 G.1 仍为 12 个核心码**，完整 142 行未落表。
2. **M-2 受保护入口只捕获 `ValueError/IndexError`**：若未来解析器新增 `KeyError/TypeError`，仍可能泄漏；当前 fuzz 未发现。
3. **DIV fuzz 的 120 组变异中大量帧会先被 CRC 拒绝**，真正进入重组解析的比例不高；确定性非法 BCD 用例已覆盖解析路径，但变异分布可再加强。
4. **83/61 图片 `L×1K`** 仍保守降级。

---

## 四、验证

```text
python3 -B tests/run_all.py → 11/11
compileall OK
git diff --check → 0
```

真实语料：福建 23 / 北京 25 基线随主套件通过。

> 本轮在自审计 SA-1 之外，又补了 B1 多记录展开与真实日历校验；未执行 `git add/commit`。

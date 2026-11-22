# SL651-Toolkit v1.5.0 修复报告

> 日期：2026-11-22
> 基线：v1.4.3（`ac1c65d`）
> 依据：`audit/audit_report_v3.0.md` + `audit/audit_review_v3.0.md`
> 测试：`python3 -B tests/run_all.py` → **12/12**
> 提交状态：按用户要求 **未执行 git add/commit**
> 后续补丁：v3.1 的 L-1/Info 修复见 `docs/fix_report_v1.5.1.md`

---

## 一、闭环清单

| 编号 | 修复 | 关键位置 |
|---|---|---|
| M-1 | SL427 类型表按 §7.3.22 表33~44 重写：0x08=4B/0.01/kW·h、0x09=2B/0.1/℃、0x0C=3B/0.1/mm、0x0F=4B/0.01/kPa、0x07=8B、0x0A=5B 位图+N×4B、0x0B=4B；0x03 流量+累计水量成对（表35/表36）；`COMP_BITS` 位序保持不动 | `sl427/constants.py` `CTRL_FUNC_MAP`/`WATER_QUALITY_SPECS`；`sl427/decoder.py` `_parse_parameter_records`/`_parse_weather`/`_parse_water_quality`/`_parse_soil_record` |
| M-2 | 统计雨量 `/10`（0.1mm）、类型字节按表54 D7~D6/D5~D0 位域；C0/81/82/B1 共用 | `sl427/decoder.py:235-257` |
| M-3 | 人工置数 F2H 固定定义符：编码器 `F2 F2 + payload`；解码器读定义符（非 F2H 时兼容旧口径 + warning），载荷不再包含定义符 | `sl651/encoder.py` `build_manual_frame`；`sl651/decoder.py` F2 分支 |
| M-4 | 47H/48H = `97 00`/`98 00`；49H = `03 10 + 2B HEX`（新旧密码，注意不是 BCD）；3AH 按表C.1、41H 按表D.1、43H 按表D.4 生成定义符；未知/变长标识符抛 `EncodeError`，支持 `(guide,len,dec)` 元组覆盖 | `sl651/encoder.py` `build_query_body`/`build_read_config_frame`/`build_init_solid_storage`/`build_reset_frame`/`build_change_password_frame`；`sl651/constants.py` `SL651_ELEMENT_DEFS`/`SL651_PARAM_DEFS_D1`/`_D4` |
| M-5 | F3/FD 固定定义符（F3H/F6H）消费到正文末尾；非固定值按声明长度兼容 + warning；FD 测试 fixture 改为 `FD F6` | `sl651/decoder.py` F3/FD 分支；`tests/test_constants_spec.py` |
| L-1 | 下行 40~43/47~49 使用附录D 命名空间（不再套用附录C 要素）；41H/43H 标识符、49H 旧/新密码；F1F1 跳过按功能码区分（49H 响应无站类） | `sl651/decoder.py` `_parse_downlink_body`/49H 响应分支 |
| L-2 | 59H/5AH 与 B0/C0 的 0x0A 按表18 `(name,unit,decimal)` 缩放；0x0A 位图 + N×4B | `sl427/constants.py` `WATER_QUALITY_SPECS`；`sl427/decoder.py` `_parse_water_quality` |
| v2.9 L-1 | `_parse_parameter_records` 返回 `(elements, consumed)`；B0/C0/81/82/FF 短数据/尾随 warning；B1 按 consumed 循环；`_parse_query_response` 8 处整除截断补尾随 warning；A1H/53H 非 30B 提示 | `sl427/decoder.py` |
| I-1 | A1H 默认保持变长 + 30B 告警；新增 `build_set_report_kinds_30(mask, intervals14)` 固定 30B 口径，供严格按 §7.2.23 的终端使用 | `sl427/decoder.py`、`sl427/encoder.py` |
| I-2 | 新增 `tests/test_spec_conformance.py`（12 组），期望值来自规约表/福建示例；更新旧断言（47/49/F2/59H/综合参数/FD/Baseline） | `tests/` |
| I-3 | 版本 1.5.0；README/project/handoff/module README/工具 README 同步；修正 `__version__` 1.4.0 残留、“7 个辅助套件”、F2 无定义符等漂移 | 文档 |

---

## 一（补）、“能修尽修”补充项

| 项 | 补充修复 |
|----|----------|
| 41H 表D.1 | 增加 `0D` 采集要素位图（4B/0，表D.2）；04~0B 信道类/0E 服务地址范围（D.3 变长）/0F 识别号（不定长）保留元组覆盖 |
| 43H 表D.4 | 增加 `97` 固态存储初始化、`98` 恢复出厂（0B/0）；20~A8 的 `N(D,d)` 行已逐行抽取并抽检 |
| A1H 固定 30B | 新增 `build_set_report_kinds_30(mask, intervals14)`（2B 位图 + 14×2B）；默认变长方法保留 |
| B1 0x0A | 同时支持“5B 位图 + N×4B”与“单参数 4B”两种形态（按 `param` 位与长度识别） |
| 固定长度告警 | 50/51/52/54/55/56/5D/5E/5F/60 与 90~96/A0 数据域长度不符时写 warning |
| ASCII 下行 | 不再把附录D 参数套成附录C 要素；暂时留空 + warning，避免伪造要素 |

## 二、行为变化（升级注意）

1. **SL427 解码值变化**（按规约修正，属于修复而非回归）：
   - 0x09 水温：从“无要素”变为 2B/0.1℃；
   - 0x0F 水压：从 `MPa` 整数变为 `kPa` 两位小数；
   - 0x08 电量：4B/0.01 `kW·h`；0x0C 蒸发：3B/0.1mm；
   - 0x07 气象：从 1 个“气象参数”变为气压/风速/风向/气温 4 个值；
   - 0x0B 土壤：变为含水率 + 采集深度 2 个值；
   - 0x03：变为“流量 + 累计水量”两个要素；
   - 0x0A 水质：B0/C0 按 5B 位图 + N×4B，59H/5AH 带小数位/单位；
   - 统计雨量：数值 ×10 修正，名称为“小时降雨量(1h)”等。
2. **SL651 线格式变化**：
   - 0x35 人工置数：正文为 `F2 F2 + 载荷`（原 `F2 + 载荷`）；
   - 47H/48H 正文为 `97 00`/`98 00`（原单字节）；
   - 49H 正文为 `03 10 + 2B HEX` ×2（原 `03 + 2B` ×2 缺 `10H` 定义符；实现时确认表65 密码数据为 2B HEX，不能用 BCD 编码）；
   - 3AH/41H/43H 按表生成定义符；未知/变长标识符改为显式报错（需元组覆盖）。
3. **解码展示变化**：
   - 下行 41H/43H/49H 不再显示“断面面积/瞬时水温”等错误要素；
   - F2 载荷不再包含定义符；
   - F3/FD 显示完整载荷字节数（真实 0x36 图片为 220B，v3.0 报告中“243B”已更正为 220B）。

---

## 三、测试与验证

- `run_all.py`：12/12（新增规约符合性 12 组）。
- 新增覆盖：
  - SL427 16 类型表 + 水温/水压/蒸发/电量/气象/土壤/流量对/水质数值与单位；
  - 统计雨量 4 类、B1 0x09/0x0B/0x0A 多记录、59H/5AH 小数位；
  - B0 非数组多记录、AFN=64 尾随、B1 尾随、A1H 长度 warning；
  - SL651 F2/F2 样本、F3/FD 固定定义符、真实 0x36 两包重组（1×F3/220B）；
  - 47/48/49/3A/41/43 正文逐字节；41H 命名空间、49H 上下行密码；
- 回归：既有 11 套件全通过（更新了 47/49/F2/59H/综合参数/FD/Baseline 的期望值）。
- 健壮性：SL427 B0/B1 随机 4 万帧（合法 CRC）+ SL651 特殊/下行 2 万帧，0 未受控异常；既有变异套件通过。
- 静态：`compileall` 通过（见验收记录）。

---

## 四、已知限制（本轮未做）

1. **3AH/41H/43H 的定义表**：
   - 3AH 使用表C.1（127 项，04/F4/F5~FC 已按注 g/表C.1 修正；05H 时段长 HH.mm 非 N(D,d)，按 2B/0 收录，显式元组可覆盖）；
   - 41H 使用表D.1 固定长度参数（01/02/03/0C/0D）；04~0B（信道类型）、0E（D.3 变长）、0F（不定长）需 `(guide,len,dec)`；
   - 43H 使用表D.4 从文本提取的固定长度参数（20~A8 + 97/98，`N(D,d)` 推导）；未逐行人工核对全部行，如现场发现个别定义不符，请用元组覆盖并回报。
2. **A1H 30B 规约矛盾**：默认仍为变长 + warning；已新增 `build_set_report_kinds_30` 固定 30B 可选口径。
3. **B1 0x0A**：已兼容“单参数 4B”与“5B 位图 + N×4B”两种形态；若现场格式不同，仍需按设备调整。
4. **0x03 单流量降级**：非标 5B-only 帧按单流量解析并 warning；标准 10B 对按表35/表36。
5. **多包图片**：F3 固定定义符已消费到末尾；83/61 的 `L×1K` 分帧仍未重组（SL427）。

---

## 五、验证记录

```text
python3 -B tests/run_all.py
  [OK] 主测试套件 (test_sl651.py)
  [OK] 盲区测试套件 (test_round1_blindspots.py)
  [OK] 模拟器集成 (test_simulator_integration.py)
  [OK] 解码器变异 (test_fuzz_decoders.py)
  [OK] SL427 参数 AFN (test_sl427_param_afn.py)
  [OK] SL427 查询 AFN (test_sl427_query_afn.py)
  [OK] SL427 控制 AFN (test_sl427_control_afn.py)
  [OK] SL651 多包重组 (test_sl651_multipacket.py)
  [OK] SL427 分帧重组 (test_sl427_multiframe.py)
  [OK] 协议契约/边界 (test_protocol_contracts.py)
  [OK] 表 C.1/G.1 常量基线 (test_constants_spec.py)
  [OK] 规约符合性 (test_spec_conformance.py)
结果: 12/12 个套件全部通过
```

---

## 六、遗留/后续建议

1. 将 v3.0 的 §5 复现脚本纳入 `tests/test_spec_conformance.py`（本轮已覆盖主要项）；
2. 对表D.4 的 135 项定义做一次逐行人工核对（当前由文本 `N(D,d)` 推导）；
3. 现场回放：用真实 RTU 的 0x09/0x0A/0x0F/0x07 帧验证 2B/位图/8B 语义；
4. 若需对外发布，建议补充 CHANGELOG 并执行 `git add/commit`（本轮按用户要求未提交）。

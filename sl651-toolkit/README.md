# SL651 水文规约工具包 v1.1.0

基于《水文监测数据通信规约 SL651-2014》和《水资源监测数据传输规约 SL/T 427-2021》实现的 Python 工具包。

**两大核心能力**：报文解码 + 设备模拟。

---

## 目录结构

```
sl651-toolkit/
├── sl651/                      # SL651 协议核心
│   ├── bcd.py                  # BCD 编解码
│   ├── crc.py                  # CRC-16/MODBUS + CRC8
│   ├── constants.py            # 101 要素表、FF 子标识符、定义符、帧结构常量
│   ├── decoder.py              # 解码器（定义符动态解析）
│   └── encoder.py              # 编码器
├── sl427/                     # SL427 协议核心
│   ├── constants.py            # 控制功能码、AFN 表、告警位
│   ├── decoder.py              # 68H 帧解析器
│   └── encoder.py              # 68H 帧编码器
├── simulator/                  # 设备模拟器
│   ├── base_station.py         # 站点基类
│   ├── generators.py           # 水位/雨量/墒情数据生成器
│   ├── water_level_station.py  # 水位站
│   ├── rain_station.py         # 雨量站
│   ├── soil_station.py         # 墒情站
│   ├── sender.py               # MqttxSender（mqttx CLI）+ TcpSender（TCP socket）
│   └── engine.py               # 定时循环引擎
├── tools/
│   ├── decode_cli.py           # 解码 CLI（sl651 / sl427 双协议）
│   └── simulate_cli.py         # 模拟器 CLI
├── examples/
│   ├── stations.yaml           # 多站点配置
├── tests/
│   └── test_sl651.py           # 11 项自测
└── requirements.txt            # 仅 PyYAML>=6.0
```

## 环境要求

- Python 3.10+
- `PyYAML>=6.0`（仅多站点配置需要）
- 模拟器 MQTT 模式需要系统安装 `mqttx` CLI：
  ```bash
  # macOS
  curl -sL https://github.com/emqx/MQTTX/releases/download/v1.13.0/mqttx-cli-macos-arm64 -o /usr/local/bin/mqttx && chmod +x /usr/local/bin/mqttx

  # Linux x64
  curl -sL https://github.com/emqx/MQTTX/releases/download/v1.13.0/mqttx-cli-linux-x64 -o /usr/local/bin/mqttx && chmod +x /usr/local/bin/mqttx
  ```

---

## 一、报文解码器

### 1.1 CLI 使用

```bash
# SL651 解码
python tools/decode_cli.py sl651 --hex "7E7E2500418D233700..."

# SL427 解码
python tools/decode_cli.py sl427 --hex "681568..."

# 文件批量解码
python tools/decode_cli.py sl651 --file messages.txt

# JSON 输出
python tools/decode_cli.py sl651 --hex "..." -o json
```

### 1.2 解码输出示例

```
========================================================================
原始报文: 7E7E2500418D23370000320030020C06230601010314F1F100418D23374BF0F0...
------------------------------------------------------------------------
中心站地址    : 25
遥测站地址    : 00418D2337
密码          : 0000
功能码        : 0x32 (定时报)
方向          : 上行（遥测站→中心站）
正文长度      : 48 字节
流水号        : 0C06
发报时间      : 2023-06-01 01:03:14
测站类别      : 4B (水库)
观测时间      : 2023-06-01 01:00
编码方式      : BCD
CRC 校验      : 通过 (接收=0x5AC6, 计算=0x5AC6)
------------------------------------------------------------------------
要素数据 (5 项):
  编码   名称                           值                 单位       原始HEX
  20    当前降水量                        0.0                 mm       000000
  3B    坝上水位                         37.865              m        00037865
  22    5分钟雨量                        0.0                 mm       000000
  26    累计雨量                         0.0                 mm       000000
  38    电池电压                         12.85               V        1285
========================================================================
```

### 1.3 Python API

```python
from sl651 import SL651Decoder
from sl427 import SL427Decoder

# SL651
r = SL651Decoder().decode_hex("7E7E...")
print(r.station_addr)
print(r.function_name)
print(r.tx_time_display)
for e in r.elements:
    print(f"  [{e.code}] {e.name}: {e.display_value}")

# SL427
r = SL427Decoder().decode_hex("68...")
print(r.afn_name)
print(r.direction)
for e in r.elements:
    print(f"  {e.name}: {e.value} {e.unit}")
```

---

## 二、设备模拟器

### 2.1 CLI 使用

```bash
# MQTT 模式（通过 mqttx CLI 发布）
python tools/simulate_cli.py --type water_level --addr 1234567890 \
    --proto mqtt --broker 192.168.1.100:1883 --interval 300

# TCP 模式（直接发送 SL651 原始帧）
python tools/simulate_cli.py --type water_level --addr 1234567890 \
    --proto sl651 --target 192.168.1.100:5001 --interval 300

# 雨量站 / 墒情站
python tools/simulate_cli.py --type rain --addr 1234567892 --proto mqtt --broker 127.0.0.1:1883
python tools/simulate_cli.py --type soil --addr 1234567893 --proto mqtt --broker 127.0.0.1:1883

# 多站点 YAML
python tools/simulate_cli.py --config examples/stations.yaml
```

### 2.2 YAML 配置

```yaml
sender:
  proto: mqtt
  broker: 127.0.0.1:1883
  topic: "sl651/{station_addr}/uplink"

stations:
  - type: water_level
    addr: "0000000001"
    interval: 60
    base_level: 5.0
  - type: rain
    addr: "0000000002"
    interval: 60
```

### 2.3 MQTT Topic

模拟器向 `{station_addr}` 占位符替换后的 topic 发送 SL651 报文 hex 字符串。

### 2.4 Python API

```python
from simulator import WaterLevelStation, MqttxSender
from simulator.engine import SimulatorEngine
from sl651 import SL651Encoder

sender = MqttxSender(host="127.0.0.1", port=1883,
                      topic_template="sl651/{station_addr}/uplink")
station = WaterLevelStation("1234567890")
engine = SimulatorEngine(sender)
engine.add_station(station, center_addr=1, password=0,
                   station_type=0x48, interval=300)
engine.start()  # Ctrl+C 停止
```

### 2.5 站点类型

| 站点 | 模拟要素 | 要素码 |
|---|---|---|
| 水位站 | 瞬时河道水位、电池电压 | `0x39`、`0x38` |
| 雨量站 | 日降水量、1h雨量、当前降水量、累计雨量、电压 | `0x1F`、`0x1A`、`0x20`、`0x26`、`0x38` |
| 墒情站 | 10/20/30/40cm 含水量、电压 | `0x10`、`0x11`、`0x12`、`0x13`、`0x38` |

---

## 三、运行测试

```bash
python tests/test_sl651.py
```

---

## 四、版本历史

- **v1.1.0**：基于 njnrs 实现重构
  - 解码器：定义符动态解析、101 要素表、FF 子标识符、状态位解码
  - 新增 SL427 解码器（68H 帧 + CRC8）
  - 模拟器：拆分 sender/engine，MQTT 改用 mqttx CLI，新增 TCP 直连模式
  - CRC 修正为 CRC-16/MODBUS，负数 BCD 编码修复
- **v1.0.0**：初始版本（GLM 生成）

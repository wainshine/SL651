# simulator — SL651 设备模拟器

## 概述

模拟水位站、雨量站、墒情站三种遥测终端，生成符合 SL651 规范的报文，通过 MQTT（mqttx CLI）或 TCP socket 推送到服务器。

## 文件清单

| 文件 | 说明 |
|------|------|
| `base_station.py` | 站点模拟器基类 `BaseStation` |
| `generators.py` | 数据生成器：水位（布朗运动+正弦周期）、雨量（降雨事件状态机）、墒情（多层含水量+温度） |
| `water_level_station.py` | 水位站 `WaterLevelStation`：瞬时河道水位(0x39) + 电池电压(0x38) |
| `rain_station.py` | 雨量站 `RainStation`：日降水/1h雨量/当前降水/累计雨量(0x26，不归零)/电压 |
| `soil_station.py` | 墒情站 `SoilStation`：10/20/30/40cm含水量 + 电压 |
| `sender.py` | 发送器：`MqttxSender`（mqttx CLI 子进程）、`TcpSender`（TCP socket 含重连） |
| `engine.py` | 定时循环引擎：`StationRunner`（单站线程）+ `SimulatorEngine`（多站管理） |

## 核心 API

### 站点

```python
from simulator import WaterLevelStation, RainStation, SoilStation

# 水位站
ws = WaterLevelStation("1234567890", base_level=5.0)
elements = ws.generate_elements()
# 返回: [(0x39, 5.023, 4, 3), (0x38, 12.57, 2, 2)]

# 雨量站（含 is_raining 属性）
rs = RainStation("1234567892")
if rs.is_raining:
    elements = rs.generate_elements()

# 水位站加报触发
ws.check_alert_trigger(threshold=0.05)  # 水位变化 > 0.05m → True
```

### 发送器

```python
from simulator import MqttxSender, TcpSender

# MQTT（需系统安装 mqttx CLI）
mqtt = MqttxSender(
    host="192.168.1.100", port=1883,
    topic_template="sl651/{station_addr}/uplink",
    username="", password="",
)

# TCP 直连（含重连）
tcp = TcpSender(host="192.168.1.100", port=5001, reconnect=True)
```

两者都实现 `Sender` 接口：`send(hex_msg: str, station_addr: str) -> bool`

### 引擎

```python
from simulator import WaterLevelStation, MqttxSender
from simulator.engine import SimulatorEngine

sender = MqttxSender(host="127.0.0.1", port=1883,
                      topic_template="sl651/{station_addr}/uplink")
station = WaterLevelStation("1234567890")

engine = SimulatorEngine(sender)
engine.add_station(
    station,
    center_addr=1,             # 中心站址
    password=0,                # SL651 密码
    station_type=0x48,         # 河道站
    interval=300,              # 上报间隔 300 秒
    function_code=0x32,        # 定时报
    enable_alert=True,         # 启用加报
    alert_threshold=0.05,      # 水位变化 0.05m 触发
)
engine.start()  # Ctrl+C 停止
```

## 依赖

- `sl651/encoder.py` — SL651Encoder 帧构造
- 外部：`PyYAML>=6.0`（YAML 多站点配置可选）
- 外部 CLI：`mqttx`（MQTT 模式）

## CLI 使用

```bash
# MQTT 模式
python tools/simulate_cli.py --type water_level --addr 1234567890 \
    --proto mqtt --broker 192.168.1.100:1883 --interval 300

# TCP 模式
python tools/simulate_cli.py --type water_level --addr 1234567890 \
    --proto sl651 --target 192.168.1.100:5001 --interval 300

# 启用加报
python tools/simulate_cli.py --type rain --addr 1234567892 \
    --proto mqtt --broker 127.0.0.1:1883 --enable-alert
```

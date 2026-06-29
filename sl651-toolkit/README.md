# SL651 水文规约工具包

基于《水文监测数据通信规约 SL651-2014》实现的 Python 工具包，提供两大核心能力：

1. **水文规约解码器** —— 解析 SL651 报文，提取帧头信息、要素数据、CRC 校验
2. **设备模拟器** —— 通过 MQTT 协议模拟水位站、雨量站、墒情站，向服务器推送 SL651 报文

---

## 目录结构

```
sl651-toolkit/
├── sl651/                          # 协议核心库
│   ├── __init__.py                 # 公共接口导出
│   ├── bcd.py                      # BCD 编解码工具
│   ├── crc.py                      # CRC-16/CCITT 校验
│   ├── constants.py                # 协议常量（要素标识符、报文类型等）
│   ├── decoder.py                  # 报文解码器
│   └── encoder.py                  # 报文编码器
├── simulator/                      # 设备模拟器
│   ├── __init__.py
│   ├── base_station.py             # 站点基类
│   ├── generators.py               # 数据生成器（模拟物理量变化）
│   ├── water_level_station.py      # 水位站
│   ├── rain_station.py             # 雨量站
│   ├── soil_station.py             # 墒情站
│   └── mqtt_publisher.py           # MQTT 发布器 + 模拟器引擎
├── tools/                          # CLI 工具
│   ├── decode_cli.py               # 解码命令行工具
│   └── simulate_cli.py             # 模拟器命令行工具
├── examples/                       # 示例
│   ├── sample_messages.txt         # 示例报文（可解码）
│   ├── stations.yaml               # 多站点配置示例
│   └── mqttx_subscribe.txt         # MQTTX 订阅配置
├── tests/
│   └── test_sl651.py               # 自测脚本
├── requirements.txt
└── README.md
```

---

## 环境要求

- Python 3.10+
- 依赖：`paho-mqtt`（模拟器必需）、`PyYAML`（多站点配置可选）

安装依赖：

```bash
pip install -r requirements.txt
```

---

## 一、水文规约解码器

### 1.1 命令行使用

```bash
# 解析单条十六进制报文
python tools/decode_cli.py "7E01000000000112340501A1002140260629103000004000523400450051800800126515897E"

# 从文件批量解析（每行一条报文，# 开头为注释）
python tools/decode_cli.py -f examples/sample_messages.txt

# 输出 JSON 格式（便于程序处理）
python tools/decode_cli.py -f examples/sample_messages.txt -o json

# 从标准输入读取
echo "7E01000000000112340501A1002140260629103000004000523400450051800800126515897E" | python tools/decode_cli.py
```

### 1.2 解码输出示例（文本格式）

```
========================================================================
原始报文: 7E01000000000112340501A1002140260629103000004000523400450051800800126515897E
------------------------------------------------------------------------
中心站地址    : 01
遥测站地址    : 0000000001
密码          : 1234
功能码        : 0x05 (定时报 / 自报)
方向          : 上行
报文类型      : A1 (定时/自报)
正文长度      : 33 字节
是否带时间    : 是
正文时间      : 2026-06-29 10:30:00
CRC 校验      : 通过
------------------------------------------------------------------------
要素数据 (3 项):
  [0040] 瞬时水位        : 5.234 m
  [0045] 日平均水位      : 5.180 m
  [0800] 电源电压        : 12.65 V
========================================================================
```

### 1.3 Python API 使用

```python
from sl651 import SL651Decoder, decode_hex

# 方式一：便捷函数
result = decode_hex("7E01000000000112340501A1002140260629103000004000523400450051800800126515897E")

# 方式二：解码器实例（可复用）
decoder = SL651Decoder()
result = decoder.decode_hex("7E...")

# 访问解析结果
print(result.center_station_addr)      # "01"
print(result.remote_station_addr)      # "0000000001"
print(result.message_type)             # "A1"
print(result.crc_ok)                   # True
print(result.body_time)                # datetime(2026, 6, 29, 10, 30, 0)

for elem in result.elements:
    print(f"{elem.identifier} {elem.name}: {elem.display_value}")

# 转为字典（便于序列化）
data = result.to_dict()
```

### 1.4 支持的要素标识符

| 分类 | 标识符    | 名称                | 单位   |
| ---- | --------- | ------------------- | ------ |
| 雨量 | 0010      | 日雨量累计值        | mm     |
| 雨量 | 0015      | 小时降雨量          | mm     |
| 雨量 | 0012      | 雨强                | mm/min |
| 水位 | 0040      | 瞬时水位            | m      |
| 水位 | 0045      | 日平均水位          | m      |
| 流量 | 0050      | 瞬时流量            | m³/s   |
| 墒情 | 0600~0605 | 10~100cm 土壤含水量 | %      |
| 墒情 | 0610~0615 | 10~100cm 土壤温度   | ℃      |
| 气象 | 0710      | 气温                | ℃      |
| 工况 | 0800      | 电源电压            | V      |
| 工况 | 0801      | 电池电压            | V      |

完整列表见 `sl651/constants.py` 中的 `ELEMENT_IDENTIFIERS`。

---

## 二、设备模拟器

### 2.1 单站点模拟（命令行）

```bash
# 模拟一个水位站，每 60 秒上报一次，推送到本地 MQTT 服务器
python tools/simulate_cli.py \
    --type water_level \
    --addr 0000000001 \
    --mqtt-host 127.0.0.1 \
    --mqtt-port 1883 \
    --interval 60

# 模拟雨量站（下雨时自动触发加报）
python tools/simulate_cli.py \
    --type rain \
    --addr 0000000002 \
    --mqtt-host 127.0.0.1 \
    --interval 60

# 模拟墒情站
python tools/simulate_cli.py \
    --type soil \
    --addr 0000000003 \
    --mqtt-host 127.0.0.1 \
    --interval 300

# 仅生成一帧报文（不连接 MQTT，用于测试）
python tools/simulate_cli.py --type water_level --addr 0000000001 --dry-run
```

### 2.2 多站点模拟（配置文件）

```bash
# 使用 YAML 配置同时启动多个站点
python tools/simulate_cli.py --config examples/stations.yaml --mqtt-host 127.0.0.1
```

配置文件格式见 `examples/stations.yaml`：

```yaml
mqtt:
  host: 127.0.0.1
  port: 1883
  topic_template: "sl651/{station_addr}/uplink"
  publish_hex_also: true

stations:
  - type: water_level
    addr: "0000000001"
    interval: 60
    base_level: 5.0
  - type: rain
    addr: "0000000002"
    interval: 60
    enable_a2_alert: true
  - type: soil
    addr: "0000000003"
    interval: 300
```

### 2.3 MQTT Topic 设计

模拟器会向以下 topic 发布消息：

| Topic                             | Payload         | 说明                      |
| --------------------------------- | --------------- | ------------------------- |
| `sl651/{station_addr}/uplink`     | 二进制 SL651 帧 | 原始报文，供服务器解析    |
| `sl651/{station_addr}/uplink/hex` | 十六进制字符串  | 便于 MQTTX 等工具直接查看 |

可通过 `--topic` 参数自定义 topic 模板，`{station_addr}` 会被替换为站点地址。

### 2.4 使用 MQTTX 订阅查看

1. 打开 MQTTX，连接到你的 MQTT 服务器
2. 订阅 topic：
   - `sl651/+/uplink/hex` —— 订阅所有站点的 hex 报文（推荐，便于查看）
   - `sl651/0000000001/uplink/hex` —— 订阅指定站点的 hex 报文
   - `sl651/+/uplink` —— 订阅所有站点的二进制报文
3. 启动模拟器后，即可在 MQTTX 中看到推送的报文

### 2.5 Python API 使用

```python
from simulator import WaterLevelStation, RainStation, SoilStation
from simulator.mqtt_publisher import MqttConfig, MqttPublisher, SimulatorEngine

# 1. 配置 MQTT
config = MqttConfig(
    host="127.0.0.1",
    port=1883,
    topic_template="sl651/{station_addr}/uplink",
)

# 2. 创建发布器并连接
publisher = MqttPublisher(config)
publisher.start()

# 3. 创建模拟器引擎，添加站点
engine = SimulatorEngine(publisher)
engine.add_station(WaterLevelStation("0000000001"), interval=60)
engine.add_station(RainStation("0000000002"), interval=60)
engine.add_station(SoilStation("0000000003"), interval=300)

# 4. 启动（阻塞，Ctrl+C 停止）
try:
    engine.start()
except KeyboardInterrupt:
    engine.stop()
    publisher.stop()
```

### 2.6 数据模拟逻辑

| 站点类型 | 模拟要素                       | 数据变化逻辑                                    |
| -------- | ------------------------------ | ----------------------------------------------- |
| 水位站   | 瞬时水位、日平均水位、电源电压 | 水位在基准值附近布朗运动 + 正弦日周期波动       |
| 雨量站   | 日雨量、小时雨量、雨强、电压   | 大部分时间无雨，随机触发降雨事件                |
| 墒情站   | 4层含水量、4层温度、电压       | 含水量缓慢回归 + 可注入降雨影响；温度日周期波动 |

---

## 三、SL651 报文结构

```
┌──────┬──────────┬──────────┬──────┬────────┬────────┬──────────┬──────────┬──────────┬──────┬──────┐
│起始符 │中心站地址│遥测站地址│ 密码 │ 功能码 │方向标志│ 报文类型 │ 正文长度 │ 报文正文 │ CRC  │结束符│
│ 7E   │  1 字节  │  5 字节  │2字节│ 1 字节 │ 1 字节 │  1 字节  │  2 字节  │  N 字节  │2字节 │ 7E   │
└──────┴──────────┴──────────┴──────┴────────┴────────┴──────────┴──────────┴──────────┴──────┴──────┘
```

- **起始符/结束符**：`0x7E`
- **中心站地址**：1 字节 BCD 编码（2 位十进制）
- **遥测站地址**：5 字节 BCD 编码（10 位十进制）
- **密码**：2 字节 BCD 编码（4 位十进制）
- **功能码**：1 字节，如 `0x05` 为定时自报
- **方向标志**：`0x00` 下行，`0x01` 上行
- **报文类型**：1 字节 BCD 编码，如 `A1` 为定时自报
- **正文长度**：2 字节 BCD 编码，表示报文正文字节数
- **报文正文**：可选时间戳 + 要素数据（标识符 + 值）
- **CRC**：2 字节，CRC-16/CCITT，计算范围从中心站地址到报文正文结束

---

## 四、运行测试

```bash
# 运行协议自测（BCD、CRC、编解码往返、站点生成）
python tests/test_sl651.py
```

预期输出：

```
============================================================
SL651 工具包自测
============================================================
>>> 测试 BCD 编解码
    OK
>>> 测试 CRC-16/CCITT
    OK
>>> 测试编码 -> 解码往返一致性
    OK
...
============================================================
所有测试通过
============================================================
```

---

## 五、常见问题

### Q1: 如何对接现有的水文平台？

平台侧需要订阅 `sl651/{station_addr}/uplink` topic，收到二进制 payload 后调用解码器解析：

```python
import paho.mqtt.client as mqtt
from sl651 import SL651Decoder

decoder = SL651Decoder()

def on_message(client, userdata, msg):
    try:
        result = decoder.decode(msg.payload)
        print(f"站点 {result.remote_station_addr} 上报:")
        for elem in result.elements:
            print(f"  {elem.name}: {elem.display_value}")
    except Exception as e:
        print(f"解析失败: {e}")

client = mqtt.Client()
client.on_message = on_message
client.connect("127.0.0.1", 1883)
client.subscribe("sl651/+/uplink")
client.loop_forever()
```

### Q2: 如何扩展新的要素标识符？

在 `sl651/constants.py` 的 `ELEMENT_IDENTIFIERS` 字典中添加条目：

```python
"0900": ("新要素名称", "单位", "数据类型", 小数位数, 数据字节数),
```

### Q3: 如何模拟 TCP 直连模式（非 MQTT）？

当前版本仅支持 MQTT 推送。如需 TCP 直连，可基于 `SL651Encoder` 自行实现 TCP 客户端，将 `station.build_a1_frame()` 生成的帧通过 socket 发送。

### Q4: 报文时间字段为什么是 2026 年？

SL651 时间字段使用 2 位 BCD 编码年份，解码时按 `2000 + 年份` 处理。模拟器默认使用当前系统时间。

---

## 六、版本说明

- **v1.0.0**：初始版本
  - 支持 SL651-2014 报文编解码
  - 支持水位站、雨量站、墒情站模拟
  - 支持 MQTT 协议推送
  - 提供 CLI 工具和 Python API
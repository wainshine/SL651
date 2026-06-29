#!/usr/bin/env python3
"""SL651 设备模拟器 CLI 工具。

通过 MQTT 协议模拟水位站、雨量站、墒情站，向服务器推送 SL651 报文。

用法示例::

    # 启动一个水位站（默认 60 秒上报一次）
    python simulate_cli.py --type water_level --addr 0000000001 \
        --mqtt-host 127.0.0.1 --mqtt-port 1883

    # 同时启动多个站点
    python simulate_cli.py --config stations.yaml

    # 单次生成一帧报文（不连接 MQTT，仅打印）
    python simulate_cli.py --type rain --addr 0000000002 --dry-run

    # 指定 topic 模板
    python simulate_cli.py --type soil --addr 0000000003 \
        --mqtt-host broker.example.com --topic "hydro/{station_addr}/data"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sl651 import bytes_to_hex_compact
from simulator import RainStation, SoilStation, WaterLevelStation
from simulator.mqtt_publisher import MqttConfig, MqttPublisher, SimulatorEngine

STATION_CLASSES = {
    "water_level": WaterLevelStation,
    "rain": RainStation,
    "soil": SoilStation,
}


def build_station(station_type: str, addr: str, center: str, password: str, **kwargs):
    """根据类型构造站点实例。"""
    cls = STATION_CLASSES.get(station_type)
    if cls is None:
        raise ValueError(f"未知站点类型: {station_type}，可选: {list(STATION_CLASSES.keys())}")
    if cls is WaterLevelStation:
        return cls(addr, center, password, base_level=kwargs.get("base_level", 5.0))
    return cls(addr, center, password)


def load_config(config_path: str) -> dict:
    """加载 YAML/JSON 配置文件。"""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"配置文件不存在: {path}")

    text = path.read_text(encoding="utf-8")
    if path.suffix in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore
        except ImportError:
            raise RuntimeError("未安装 PyYAML，请执行: pip install pyyaml")
        return yaml.safe_load(text)
    else:
        return json.loads(text)


def run_dry_run(args) -> int:
    """单次生成报文并打印（不连接 MQTT）。"""
    station = build_station(args.type, args.addr, args.center, args.password)
    now = datetime.now()
    frame = station.build_a1_frame(body_time=now)
    hex_str = bytes_to_hex_compact(frame)

    print("=" * 72)
    print(f"站点类型    : {station.name}")
    print(f"站点地址    : {args.addr}")
    print(f"中心站地址  : {args.center}")
    print(f"报文时间    : {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"报文长度    : {len(frame)} 字节")
    print("-" * 72)
    print(f"HEX (紧凑)  : {hex_str}")
    print("-" * 72)
    print("HEX (分组)  :")
    for i in range(0, len(hex_str), 32):
        chunk = hex_str[i : i + 32]
        grouped = " ".join(chunk[j : j + 2] for j in range(0, len(chunk), 2))
        print(f"  {grouped}")
    print("=" * 72)
    print()
    print("可在 MQTTX 中将以上 HEX 字符串作为 payload 发布到对应 topic。")
    print("或使用本工具的 MQTT 模式自动发布: 去掉 --dry-run 并指定 --mqtt-host。")
    return 0


def run_mqtt_simulator(args) -> int:
    """启动 MQTT 模拟器。"""
    # 构造 MQTT 配置
    mqtt_config = MqttConfig(
        host=args.mqtt_host,
        port=args.mqtt_port,
        username=args.mqtt_username,
        password=args.mqtt_password,
        topic_template=args.topic,
        publish_hex_also=not args.no_hex,
    )
    publisher = MqttPublisher(mqtt_config)

    # 构造引擎
    engine = SimulatorEngine(publisher)

    # 添加站点
    if args.config:
        cfg = load_config(args.config)
        for station_cfg in cfg.get("stations", []):
            station = build_station(
                station_cfg["type"],
                station_cfg["addr"],
                station_cfg.get("center", "01"),
                station_cfg.get("password", "1234"),
                base_level=station_cfg.get("base_level", 5.0),
            )
            engine.add_station(
                station,
                interval=station_cfg.get("interval", 60),
                enable_a2_alert=station_cfg.get("enable_a2_alert", True),
            )
    else:
        station = build_station(args.type, args.addr, args.center, args.password)
        engine.add_station(station, interval=args.interval, enable_a2_alert=not args.no_a2)

    # 启动
    try:
        publisher.start()
        engine.start()
    except KeyboardInterrupt:
        pass
    finally:
        engine.stop()
        publisher.stop()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SL651 设备模拟器 - 通过 MQTT 推送水文/雨量/墒情数据",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 单次生成一帧报文（不连接 MQTT）
  %(prog)s --type water_level --addr 0000000001 --dry-run

  # 启动水位站，每 60 秒上报一次
  %(prog)s --type water_level --addr 0000000001 \\
      --mqtt-host 127.0.0.1 --mqtt-port 1883 --interval 60

  # 启动雨量站（含加报）
  %(prog)s --type rain --addr 0000000002 --mqtt-host broker.example.com

  # 通过配置文件启动多个站点
  %(prog)s --config stations.yaml --mqtt-host broker.example.com

可用站点类型: water_level(水位站), rain(雨量站), soil(墒情站)
""",
    )
    parser.add_argument(
        "--type",
        choices=list(STATION_CLASSES.keys()),
        help="站点类型（单站点模式）",
    )
    parser.add_argument("--addr", help="遥测站地址，10 位数字字符串（如 0000000001）")
    parser.add_argument("--center", default="01", help="中心站地址，默认 01")
    parser.add_argument("--password", default="1234", help="密码，默认 1234")
    parser.add_argument("--interval", type=float, default=60.0, help="定时上报间隔（秒），默认 60")
    parser.add_argument("--no-a2", action="store_true", help="禁用加报（雨量站）")
    parser.add_argument("--base-level", type=float, default=5.0, help="水位基准值（m），默认 5.0")

    # MQTT 选项
    parser.add_argument("--mqtt-host", default="127.0.0.1", help="MQTT 服务器地址，默认 127.0.0.1")
    parser.add_argument("--mqtt-port", type=int, default=1883, help="MQTT 端口，默认 1883")
    parser.add_argument("--mqtt-username", default="", help="MQTT 用户名")
    parser.add_argument("--mqtt-password", default="", help="MQTT 密码")
    parser.add_argument(
        "--topic",
        default="sl651/{station_addr}/uplink",
        help="MQTT topic 模板，{station_addr} 会被替换，默认 sl651/{station_addr}/uplink",
    )
    parser.add_argument(
        "--no-hex",
        action="store_true",
        help="不发布 hex 字符串版本（默认会同时发布二进制和 hex 两个版本）",
    )

    # 其他
    parser.add_argument("--config", help="站点配置文件（YAML/JSON），启用多站点模式")
    parser.add_argument("--dry-run", action="store_true", help="仅生成一帧报文并打印，不连接 MQTT")
    parser.add_argument("-v", "--verbose", action="store_true", help="详细日志")

    args = parser.parse_args()

    # 配置日志
    import logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # 参数校验
    if args.dry_run:
        if not args.type or not args.addr:
            parser.error("--dry-run 模式需要 --type 和 --addr")
        return run_dry_run(args)

    if args.config:
        return run_mqtt_simulator(args)

    if not args.type or not args.addr:
        parser.error("单站点模式需要 --type 和 --addr（或使用 --config 启动多站点）")
    return run_mqtt_simulator(args)


if __name__ == "__main__":
    sys.exit(main())

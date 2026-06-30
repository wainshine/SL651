#!/usr/bin/env python3
"""SL651 设备模拟器。

通过 mqttx CLI 或 TCP 发送 SL651 报文。

用法::

    # MQTTX 模式
    python simulate_cli.py --type water_level --addr 1234567890 \\
        --proto mqtt --broker 192.168.1.100:1883 --topic "hydro/{station_addr}/uplink"

    # TCP 模式（原始 SL651 帧）
    python simulate_cli.py --type water_level --addr 1234567890 \\
        --proto sl651 --target 192.168.1.100:5001

    # 多站点 YAML
    python simulate_cli.py --config stations.yaml
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simulator import (
    MqttxSender,
    RainStation,
    SoilStation,
    TcpSender,
    WaterLevelStation,
)
from simulator.engine import SimulatorEngine
from simulator.sender import SendError

STATION_MAP = {
    "water_level": WaterLevelStation,
    "rain": RainStation,
    "soil": SoilStation,
}

STATION_TYPE_MAP = {
    "water_level": 0x48,  # 河道
    "rain": 0x50,         # 降水
    "soil": 0x4D,         # 墒情
}


def parse_host_port(s: str) -> tuple[str, int]:
    parts = s.rsplit(":", 1)
    host = parts[0]
    port = int(parts[1]) if len(parts) > 1 else 1883
    return host, port


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SL651 设备模拟器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--type", choices=list(STATION_MAP), default="water_level",
                        help="站点类型 (默认 water_level)")
    parser.add_argument("--addr", default="1234567890",
                        help="遥测站地址，10位十六进制 (默认 1234567890)")
    parser.add_argument("--proto", choices=["mqtt", "sl651"], default="mqtt",
                        help="协议: mqtt (mqttx CLI) / sl651 (TCP) (默认 mqtt)")
    parser.add_argument("--broker", default="127.0.0.1:1883",
                        help="MQTT broker 地址:端口 (默认 127.0.0.1:1883)")
    parser.add_argument("--target", default="127.0.0.1:5001",
                        help="TCP 目标地址:端口 (默认 127.0.0.1:5001)")
    parser.add_argument("--topic", default="sl651/{station_addr}/uplink",
                        help="MQTT topic 模板，{station_addr} 占位 (默认 sl651/{station_addr}/uplink)")
    parser.add_argument("--username", default="", help="MQTT 用户名")
    parser.add_argument("--password", default="", help="MQTT 密码")
    parser.add_argument("--center", type=int, default=1,
                        help="中心站地址 (默认 1)")
    parser.add_argument("--pwd", type=int, default=0,
                        help="SL651 密码 (默认 0)")
    parser.add_argument("--interval", type=float, default=300.0,
                        help="上报间隔，秒 (默认 300)")
    parser.add_argument("--base-level", type=float, default=5.0,
                        help="水位基准值 (默认 5.0)")
    parser.add_argument("--function-code", type=lambda x: int(x, 16), default=0x32,
                        help="功能码 hex (默认 32=定时报)")
    parser.add_argument("--enable-alert", action="store_true", default=False,
                        help="启用加报（雨量站下雨时/水位站越限时发送0x33帧）")
    parser.add_argument("--alert-threshold", type=float, default=0.05,
                        help="水位站加报阈值，米 (默认 0.05)")
    parser.add_argument("--config", help="YAML 多站点配置文件")
    parser.add_argument("-v", "--verbose", action="store_true", help="详细日志")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    logger = logging.getLogger("simulator")

    if args.config:
        return _load_config(args.config)

    station_cls = STATION_MAP[args.type]
    station_kwargs = {"station_addr": args.addr}
    if args.type == "water_level":
        station_kwargs["base_level"] = args.base_level

    station = station_cls(**station_kwargs)
    station_type = STATION_TYPE_MAP[args.type]

    if args.proto == "mqtt":
        host, port = parse_host_port(args.broker)
        sender = MqttxSender(
            host=host, port=port,
            username=args.username, password=args.password,
            topic_template=args.topic,
        )
    else:
        host, port = parse_host_port(args.target)
        sender = TcpSender(host=host, port=port, reconnect=True)

    try:
        engine = SimulatorEngine(sender)
        engine.add_station(
            station,
            center_addr=args.center,
            password=args.pwd,
            station_type=station_type,
            interval=args.interval,
            function_code=args.function_code,
            enable_alert=args.enable_alert,
            alert_threshold=args.alert_threshold,
        )
        engine.start()
    except SendError as e:
        logger.error(str(e))
        return 1

    return 0


def _load_config(config_path: str) -> int:
    try:
        import yaml
    except ImportError:
        print("需要 PyYAML: pip install PyYAML>=6.0", file=sys.stderr)
        return 1

    with open(config_path) as f:
        config = yaml.safe_load(f)

    sender_cfg = config.get("sender", {})
    proto = sender_cfg.get("proto", "mqtt")
    if proto == "mqtt":
        host, port = parse_host_port(sender_cfg.get("broker", "127.0.0.1:1883"))
        sender = MqttxSender(
            host=host, port=port,
            username=sender_cfg.get("username", ""),
            password=sender_cfg.get("password", ""),
            topic_template=sender_cfg.get("topic", "sl651/{station_addr}/uplink"),
        )
    else:
        host, port = parse_host_port(sender_cfg.get("target", "127.0.0.1:5001"))
        sender = TcpSender(host=host, port=port, reconnect=True)

    engine = SimulatorEngine(sender)
    for sc in config.get("stations", []):
        stype = sc.get("type", "water_level")
        cls = STATION_MAP[stype]
        kwargs = {"station_addr": str(sc.get("addr", "1234567890"))}
        if stype == "water_level":
            kwargs["base_level"] = sc.get("base_level", 5.0)

        station = cls(**kwargs)
        station_type = STATION_TYPE_MAP[stype]
        engine.add_station(
            station,
            center_addr=sc.get("center", 1),
            password=sc.get("password", 0),
            station_type=station_type,
            interval=sc.get("interval", 300),
            function_code=sc.get("function_code", 0x32),
            enable_alert=sc.get("enable_alert", False),
            alert_threshold=sc.get("alert_threshold", 0.05),
        )

    engine.start()
    return 0


if __name__ == "__main__":
    sys.exit(main())

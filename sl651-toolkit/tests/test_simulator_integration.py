#!/usr/bin/env python3
"""模拟器端到端集成测试。

覆盖：
- StationRunner._run 全链路（生成要素 → 编码 → 发送 → 解码断言）
- 雨量站加报边沿（真实 _run 路径）
- TcpSender 真实 TCP 收发（本地 socket 服务端）
"""

from __future__ import annotations

import socket
import sys
import threading
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sl651 import SL651Decoder, SL651Encoder
from simulator import RainStation, WaterLevelStation
from simulator.engine import SimulatorEngine, StationRunner
from simulator.sender import Sender, TcpSender

FAILURES: list[str] = []


class RecordingSender(Sender):
    """内存发送器，记录所有发出的报文。"""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send(self, hex_msg: str, station_addr: str = "") -> bool:
        self.sent.append((hex_msg, station_addr))
        return True

    def close(self) -> None:
        pass


def _drive(runner: StationRunner, cycles: int) -> None:
    """驱动 StationRunner._run 指定周期后停止。"""
    counter = {"n": 0}

    def fake_wait(_timeout):
        counter["n"] += 1
        if counter["n"] >= cycles:
            runner._stop.set()

    runner._stop.wait = fake_wait  # type: ignore[method-assign]
    runner._run()


def test_engine_water_level_end_to_end() -> None:
    """水位站：引擎全链路 3 周期，每帧可解码且要素正确。"""
    sender = RecordingSender()
    station = WaterLevelStation("1234567890", base_level=5.0)
    enc = SL651Encoder(station_addr="1234567890", station_type=0x48)
    runner = StationRunner(station, enc, sender, interval=0.0, function_code=0x32)
    _drive(runner, 3)

    assert len(sender.sent) == 3, f"应发送 3 帧, 实际 {len(sender.sent)}"
    decoder = SL651Decoder()
    for hex_msg, addr in sender.sent:
        assert addr == "1234567890"
        r = decoder.decode_hex(hex_msg)
        assert r.crc_ok, "CRC 应通过"
        assert r.function_code == 0x32
        assert r.station_addr == "1234567890"
        codes = {e.code for e in r.elements}
        assert "39" in codes and "38" in codes, f"缺要素: {codes}"
    print(f"    3 帧全链路解码通过 ({len(sender.sent)} 帧)")


def test_engine_rain_alert_edge() -> None:
    """雨量站：持续降雨 3 周期只加报 1 次。"""
    sender = RecordingSender()
    station = RainStation("1234567892")
    enc = SL651Encoder(station_addr="1234567892", station_type=0x50)
    runner = StationRunner(station, enc, sender, interval=0.0,
                           enable_alert=True)
    station.rain_gen.raining = True
    station.rain_gen.rain_remaining_minutes = 9999
    _drive(runner, 3)

    decoder = SL651Decoder()
    funcs = [decoder.decode_hex(h).function_code for h, _ in sender.sent]
    assert funcs.count(0x32) == 3, f"应 3 条定时报: {funcs}"
    assert funcs.count(0x33) == 1, f"应只加报 1 次: {funcs}"
    print(f"    定时报={funcs.count(0x32)}, 加报={funcs.count(0x33)} OK")


def test_engine_add_station() -> None:
    """SimulatorEngine.add_station 注册站点且不崩。"""
    engine = SimulatorEngine(RecordingSender())
    engine.add_station(WaterLevelStation("1234567890"))
    engine.add_station(RainStation("1234567892"))
    assert len(engine.runners) == 2
    print("    2 站点注册 OK")


def test_tcp_sender_end_to_end() -> None:
    """TcpSender 真实 TCP 收发：本地服务端收到完整帧并可解码。"""
    received: list[bytes] = []
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    def server() -> None:
        try:
            conn, _ = srv.accept()
        except OSError:
            return
        conn.settimeout(2.0)
        data = b""
        try:
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                data += chunk
                if len(data) >= 14:
                    body_len = ((data[11] & 0x0F) << 8) | data[12]
                    if len(data) >= 14 + body_len + 3:
                        break
        except socket.timeout:
            pass
        received.append(data)
        conn.close()

    thread = threading.Thread(target=server, daemon=True)
    thread.start()

    enc = SL651Encoder(station_addr="1234567890", station_type=0x48)
    frame = enc.build_timing_frame([(0x39, 5.123, 4, 3)],
                                   obs_time=datetime(2026, 9, 14, 10, 0))
    sender = TcpSender("127.0.0.1", port, timeout=3)
    try:
        ok = sender.send(frame.hex().upper(), "1234567890")
        assert ok, "TCP 发送应成功"
        thread.join(timeout=3)
    finally:
        sender.close()
        srv.close()

    assert received, "服务端未收到数据"
    r = SL651Decoder().decode(received[0])
    assert r.crc_ok, "TCP 收到的帧 CRC 应通过"
    assert r.function_code == 0x32
    wl = [e for e in r.elements if e.code == "39"]
    assert wl and abs(float(wl[0].value) - 5.123) < 0.001, \
        f"水位值不符: {[e.value for e in wl]}"
    print(f"    TCP 收到 {len(received[0])} 字节, 解码通过")


def main() -> int:
    print("=" * 60)
    print("模拟器端到端集成测试")
    print("=" * 60)
    tests = [
        ("引擎水位站全链路", test_engine_water_level_end_to_end),
        ("引擎雨量加报边沿", test_engine_rain_alert_edge),
        ("引擎站点注册", test_engine_add_station),
        ("TcpSender 端到端", test_tcp_sender_end_to_end),
    ]
    for name, fn in tests:
        print(f">>> {name}")
        try:
            fn()
        except Exception as e:
            print(f"    ❌ 失败: {e}")
            import traceback
            traceback.print_exc()
            FAILURES.append(f"{name}: {e}")
    print()
    if FAILURES:
        print(f"❌ 失败 {len(FAILURES)} 项:")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("✅ 模拟器集成测试全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())

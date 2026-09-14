#!/usr/bin/env python3
"""统一测试入口：依次运行主测试套件与盲区测试套件。

用法:
    python3 tests/run_all.py

返回码: 0=全部通过, 1=存在失败套件。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SUITES = [
    ("主测试套件 (test_sl651.py)", HERE / "test_sl651.py"),
    ("盲区测试套件 (test_round1_blindspots.py)", HERE / "test_round1_blindspots.py"),
    ("模拟器集成 (test_simulator_integration.py)", HERE / "test_simulator_integration.py"),
    ("解码器变异 (test_fuzz_decoders.py)", HERE / "test_fuzz_decoders.py"),
    ("SL427 参数 AFN (test_sl427_param_afn.py)", HERE / "test_sl427_param_afn.py"),
    ("SL427 查询 AFN (test_sl427_query_afn.py)", HERE / "test_sl427_query_afn.py"),
    ("SL427 控制 AFN (test_sl427_control_afn.py)", HERE / "test_sl427_control_afn.py"),
    ("SL651 多包重组 (test_sl651_multipacket.py)", HERE / "test_sl651_multipacket.py"),
]


def main() -> int:
    print("#" * 64)
    print("# SL651-Toolkit 统一测试入口")
    print("#" * 64)
    results = []
    for name, script in SUITES:
        print(f"\n>>> 运行 {name}")
        proc = subprocess.run([sys.executable, "-B", str(script)])
        results.append((name, proc.returncode))

    print("\n" + "#" * 64)
    print("# 汇总")
    print("#" * 64)
    failed = 0
    for name, code in results:
        status = "通过" if code == 0 else f"失败(exit={code})"
        print(f"  [{'OK' if code == 0 else 'FAIL'}] {name}: {status}")
        if code != 0:
            failed += 1
    if failed:
        print(f"\n结果: {failed}/{len(results)} 个套件失败")
        return 1
    print(f"\n结果: {len(results)}/{len(results)} 个套件全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())

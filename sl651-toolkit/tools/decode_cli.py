#!/usr/bin/env python3
"""SL651 报文解码 CLI 工具。

用法示例::

    # 解析十六进制字符串
    python decode_cli.py "7E 01 12 34 56 78 90 12 34 05 01 A1 ..."

    # 从文件读取（每行一条报文）
    python decode_cli.py -f messages.txt

    # 输出 JSON
    python decode_cli.py -f messages.txt -o json

    # 从标准输入读取
    echo "7E..." | python decode_cli.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 支持直接运行（python decode_cli.py）和模块运行（python -m tools.decode_cli）
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sl651 import SL651Decoder, bytes_to_hex_compact
from sl651.decoder import DecodeError


def format_text(result) -> str:
    """格式化为可读文本。"""
    lines = []
    lines.append("=" * 72)
    lines.append(f"原始报文: {bytes_to_hex_compact(result.raw_frame)}")
    lines.append("-" * 72)
    lines.append(f"中心站地址    : {result.center_station_addr}")
    lines.append(f"遥测站地址    : {result.remote_station_addr}")
    lines.append(f"密码          : {result.password}")
    lines.append(f"功能码        : 0x{result.function_code:02X} ({result.function_desc})")
    lines.append(f"方向          : {result.direction_desc}")
    lines.append(f"报文类型      : {result.message_type} ({result.message_type_desc})")
    lines.append(f"正文长度      : {result.body_length} 字节")
    lines.append(f"是否带时间    : {'是' if result.has_time else '否'}")
    if result.body_time:
        lines.append(f"正文时间      : {result.body_time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"CRC 校验      : {'通过' if result.crc_ok else '失败'} "
                 f"(接收=0x{result.crc_received:04X}, 计算=0x{result.crc_calculated:04X})")
    lines.append("-" * 72)
    if result.elements:
        lines.append(f"要素数据 ({len(result.elements)} 项):")
        lines.append(f"  {'标识符':<8} {'名称':<20} {'值':<25} {'原始HEX':<15}")
        lines.append(f"  {'-'*8} {'-'*20} {'-'*25} {'-'*15}")
        for el in result.elements:
            lines.append(
                f"  {el.identifier:<8} {el.name:<20} {el.display_value:<25} {bytes_to_hex_compact(el.raw_bytes):<15}"
            )
    else:
        lines.append("要素数据: 无")
    lines.append("=" * 72)
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SL651 水文规约报文解码工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s "7E0112345678901234050141..."
  %(prog)s -f messages.txt
  %(prog)s -f messages.txt -o json
  echo "7E..." | %(prog)s
""",
    )
    parser.add_argument("hex", nargs="?", help="十六进制报文字符串（可含空格/换行）")
    parser.add_argument("-f", "--file", help="从文件读取报文（每行一条）")
    parser.add_argument(
        "-o",
        "--output",
        choices=["text", "json"],
        default="text",
        help="输出格式，默认 text",
    )
    parser.add_argument(
        "--raw-only",
        action="store_true",
        help="仅输出原始报文（用于校验）",
    )
    args = parser.parse_args()

    # 收集待解码的报文
    messages: list[str] = []
    if args.file:
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"错误: 文件不存在: {file_path}", file=sys.stderr)
            return 1
        for line in file_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                messages.append(line)
    elif args.hex:
        messages.append(args.hex)
    else:
        # 从标准输入读取
        stdin_data = sys.stdin.read().strip()
        if stdin_data:
            for line in stdin_data.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    messages.append(line)

    if not messages:
        parser.print_help()
        return 1

    decoder = SL651Decoder()
    results = []
    errors = []
    for i, msg in enumerate(messages, 1):
        try:
            result = decoder.decode_hex(msg)
            results.append(result)
        except DecodeError as e:
            errors.append((i, msg, str(e)))
        except Exception as e:
            errors.append((i, msg, f"未知错误: {e}"))

    # 输出
    if args.output == "json":
        output = {
            "total": len(messages),
            "success": len(results),
            "failed": len(errors),
            "results": [r.to_dict() for r in results],
            "errors": [{"index": idx, "message": msg, "error": err} for idx, msg, err in errors],
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        for r in results:
            print(format_text(r))
            print()
        if errors:
            print("=" * 72)
            print(f"解码失败 ({len(errors)} 条):")
            for idx, msg, err in errors:
                print(f"  第 {idx} 条: {err}")
                print(f"    报文: {msg[:80]}{'...' if len(msg) > 80 else ''}")

    return 0 if not errors else 2


if __name__ == "__main__":
    sys.exit(main())

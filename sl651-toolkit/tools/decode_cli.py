#!/usr/bin/env python3
"""SL651 / SL427 水文规约报文解码工具。

用法::

    # SL651 解码
    python decode_cli.py sl651 --hex "7E7E25..."
    python decode_cli.py sl651 --file samples.txt

    # SL427 解码
    python decode_cli.py sl427 --hex "68..."
    python decode_cli.py sl427 --file sl427_samples.txt

    # JSON 输出
    python decode_cli.py sl651 --hex "..." -o json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sl651.decoder import DecodeError as SL651DecodeError, SL651Decoder
from sl427.decoder import DecodeError as SL427DecodeError, SL427Decoder


def _mask_center(value: str) -> str:
    """中心站地址仅 2 个 HEX 字符，必须整体遮蔽（原 [:2]+"**" 是假脱敏）。"""
    return "**"


def _mask_station(value: str) -> str:
    """遥测站地址保留前 1 字节（2 个 HEX 字符），其余遮蔽。"""
    if not value:
        return value
    return value[:2] + "********"


def _mask_addr(value: str) -> str:
    """SL427 地址域脱敏：保留方式标签，遮蔽行政区划/站址/编码。"""
    if not value:
        return value
    if value.startswith("方式1"):
        return "方式1 行政区划:****** 站址:**** (已脱敏)"
    if value.startswith("方式2"):
        return "方式2 站点编码:******** (已脱敏)"
    return "**"


def _mask_raw(hex_str: str, show_raw: bool = False, function_code: int | None = None) -> str:
    """原始报文脱敏：默认只显示前缀/长度/功能码，--show-raw 时原样。"""
    if show_raw:
        return hex_str
    prefix = hex_str[:4].upper() if len(hex_str) >= 4 else hex_str.upper()
    n = len(hex_str) // 2
    fc = f"，func=0x{function_code:02X}" if function_code is not None else ""
    return f"{prefix}…（{n} 字节{fc}，已脱敏）"


def _mask_error(msg: str, show_raw: bool = False) -> str:
    """错误信息不回显完整报文。"""
    return _mask_raw(msg, show_raw=show_raw)


def format_sl651(result, show_raw: bool = False) -> str:
    lines = []
    lines.append("=" * 72)
    lines.append(f"原始报文: {_mask_raw(result.hex_input, show_raw, result.function_code)}")
    lines.append("-" * 72)
    lines.append(f"中心站地址    : {_mask_center(result.center_addr)}")
    lines.append(f"遥测站地址    : {_mask_station(result.station_addr)}")
    lines.append(f"功能码        : 0x{result.function_code:02X} ({result.function_name})")
    lines.append(f"方向          : {result.direction_label}")
    lines.append(f"正文长度      : {result.body_length} 字节")
    lines.append(f"流水号        : {result.serial}")
    lines.append(f"发报时间      : {result.tx_time_display}")
    if result.station_type:
        lines.append(f"测站类别      : {result.station_type} ({result.station_type_name})")
    if result.obs_time_display:
        lines.append(f"观测时间      : {result.obs_time_display}")
    lines.append(f"编码方式      : {result.encoding}")
    lines.append(
        f"CRC 校验      : {'通过' if result.crc_ok else '失败'} "
        f"(接收=0x{result.crc_received:04X}, 计算=0x{result.crc_calculated:04X})"
    )
    for w in getattr(result, "warnings", []) or []:
        lines.append(f"告警          : {w}")
    lines.append("-" * 72)
    if result.elements:
        lines.append(f"要素数据 ({len(result.elements)} 项):")
        lines.append(f"  {'编码':<6} {'名称':<28} {'值':<25} {'单位':<8} {'原始HEX'}")
        lines.append(f"  {'-'*6} {'-'*28} {'-'*25} {'-'*8} {'-'*12}")
        for el in result.elements:
            lines.append(
                f"  {el.code:<6} {el.name:<28} {str(el.display_value):<25} {el.unit:<8} {el.raw}"
            )
    else:
        lines.append("要素数据: 无")
    lines.append("=" * 72)
    return "\n".join(lines)


def format_sl427(result, show_raw: bool = False) -> str:
    lines = []
    lines.append("=" * 72)
    lines.append(f"原始报文: {_mask_raw(result.hex_input, show_raw, result.afn)}")
    lines.append("-" * 72)
    lines.append(f"方向          : {result.direction}")
    lines.append(f"控制功能码    : {result.ctrl_func_name}")
    lines.append(f"地址          : {_mask_addr(result.addr_display)}")
    lines.append(f"AFN           : 0x{result.afn:02X} ({result.afn_name})")
    lines.append(f"用户数据长度  : {result.data_len} 字节")
    lines.append(
        f"CRC8 校验     : {'通过' if result.crc_ok else '失败'} "
        f"(接收=0x{result.crc_recv:02X}, 计算=0x{result.crc_calc:02X})"
    )
    for w in getattr(result, "warnings", []) or []:
        lines.append(f"告警          : {w}")
    lines.append("-" * 72)
    if result.special_info:
        if result.special_info.get("type") == "heart":
            lines.append(f"心跳类型: {result.special_info.get('name')}")
    if result.elements:
        lines.append(f"数据要素 ({len(result.elements)} 项):")
        lines.append(f"  {'名称':<30} {'值':<28} {'单位':<8} {'原始HEX'}")
        lines.append(f"  {'-'*30} {'-'*28} {'-'*8} {'-'*12}")
        for el in result.elements:
            lines.append(
                f"  {el.name:<30} {str(el.value):<28} {el.unit:<8} {el.raw}"
            )
    else:
        lines.append("数据要素: 无")
    lines.append("=" * 72)
    return "\n".join(lines)


def _sanitize_dict(d: dict) -> dict:
    """JSON 输出脱敏：与 text 输出一致。"""
    d = dict(d)
    if "password" in d:
        d["password"] = "****"
    if "center_addr" in d and d["center_addr"]:
        d["center_addr"] = _mask_center(d["center_addr"])
    if "station_addr" in d and d["station_addr"]:
        d["station_addr"] = _mask_station(d["station_addr"])
    if "addr" in d and d["addr"]:
        d["addr"] = _mask_addr(d["addr"])
    return d


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SL651 / SL427 水文规约报文解码工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s sl651 --hex "7E7E25..."
  %(prog)s sl427 --hex "68..."
  %(prog)s sl651 --file messages.txt -o json
""",
    )
    sub = parser.add_subparsers(dest="protocol", help="协议类型")

    p651 = sub.add_parser("sl651", help="SL651-2014 水文监测数据通信规约")

    p427 = sub.add_parser("sl427", help="SL427-2021 水资源监测数据传输规约")

    for p in (p651, p427):
        src = p.add_mutually_exclusive_group()
        src.add_argument("--hex", help="十六进制报文字符串")
        src.add_argument("--file", "-f", help="从文件读取报文（每行一条）")
        p.add_argument("--output", "-o", choices=["text", "json"], default="text", help="输出格式")
        p.add_argument("--show-raw", action="store_true", default=False,
                       help="显示完整原始报文（仅本地调试；默认脱敏）")

    args = parser.parse_args()

    if args.protocol not in ("sl651", "sl427"):
        parser.print_help()
        return 1

    messages = []
    if args.file:
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"错误: 文件不存在: {file_path}", file=sys.stderr)
            return 1
        try:
            lines = file_path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError) as e:
            print(f"错误: 文件读取失败: {e}", file=sys.stderr)
            return 1
        for line in lines:
            line = line.strip()
            if line and not line.startswith("#"):
                messages.append(line)
    elif args.hex:
        messages.append(args.hex)
    elif not sys.stdin.isatty():
        stdin_data = sys.stdin.read().strip()
        if stdin_data:
            for line in stdin_data.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    messages.append(line)

    if not messages:
        parser.print_help()
        return 1

    results = []
    errors = []

    if args.protocol == "sl651":
        decoder = SL651Decoder()
        err_cls = SL651DecodeError
    else:
        decoder = SL427Decoder()
        err_cls = SL427DecodeError

    for i, msg in enumerate(messages, 1):
        try:
            result = decoder.decode_hex(msg)
            results.append(result)
        except err_cls as e:
            errors.append((i, msg, str(e)))
        except Exception as e:
            errors.append((i, msg, f"未知错误: {e}"))

    if args.output == "json":
        output = {
            "total": len(messages),
            "success": len(results),
            "failed": len(errors),
            "results": [_sanitize_dict(r.to_dict()) for r in results],
            "errors": [{"index": idx, "message": _mask_error(msg, args.show_raw),
                        "error": err} for idx, msg, err in errors],
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        fmt_fn = format_sl651 if args.protocol == "sl651" else format_sl427
        for r in results:
            print(fmt_fn(r, show_raw=args.show_raw))
            print()
        if errors:
            print("=" * 72)
            print(f"解码失败 ({len(errors)} 条):")
            for idx, msg, err in errors:
                print(f"  第 {idx} 条: {err}")
                print(f"    报文: {_mask_error(msg, args.show_raw)}")

    return 0 if not errors else 2


if __name__ == "__main__":
    sys.exit(main())

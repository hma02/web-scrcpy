#!/usr/bin/env python3
"""
Reproduce and inspect header corruption similar to multi-device stream issue.

This script crafts three per-device opening payloads:
1) valid header for device 1
2) valid header for device 2
3) corrupted/midstream-like bytes containing an OpusHead-like prefix

Run:
    python unit_tester/repro_multid_header_corruption.py
"""

import struct


def parse_header_like_frontend(data: bytes):
    """Mirror static/js/video_parser.js first header parsing path."""
    if len(data) < 76:
        raise ValueError("Need at least 76 bytes")

    name_bytes = data[:64]
    name = name_bytes.decode("utf-8", errors="replace")
    stream_id, width, height = struct.unpack(">iii", data[64:76])

    invalid = width > 5000 or height > 5000 or width < 100 or height < 100
    applied_width, applied_height = (720, 1400) if invalid else (width, height)

    return {
        "name": name,
        "name_printable": name.replace("\x00", ""),
        "name_hex": name_bytes[:24].hex(" "),
        "stream_id": stream_id,
        "raw_width": width,
        "raw_height": height,
        "invalid_dimensions": invalid,
        "applied_width": applied_width,
        "applied_height": applied_height,
        "dims_hex": data[64:76].hex(" "),
    }


def make_valid_header(device_name: str, width: int, height: int):
    encoded = device_name.encode("utf-8")
    padded_name = encoded + b"\x00" * (64 - len(encoded))
    dims = struct.pack(">iii", 0, width, height)
    return padded_name + dims


def make_corrupted_header():
    # Simulate the user-observed garbage parser input that starts with OpusHead-like bytes.
    prefix = b"pus\x81\x13OpusHead\x01\x028\x01\xff\xf1I\"\x96-\x03\x89\xfa\xfeI\"\x81|\x11\x03\xfa\xfe\xfa"
    name_like = (prefix + b"\x00" * 64)[:64]

    # Width/height bytes chosen to mimic bad parse: width=580241969, height=3
    dims = struct.pack(">iii", 0, 580241969, 3)
    return name_like + dims


def main():
    cases = [
        ("device_1", make_valid_header("SM-N9500", 720, 1480)),
        ("device_2", make_valid_header("SM-G960W", 720, 1480)),
        ("device_3_corrupted", make_corrupted_header()),
    ]

    for label, payload in cases:
        parsed = parse_header_like_frontend(payload)
        print(f"\\n[{label}]")
        for k, v in parsed.items():
            print(f"{k}: {v}")


if __name__ == "__main__":
    main()

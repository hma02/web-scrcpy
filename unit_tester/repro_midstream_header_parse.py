#!/usr/bin/env python3
"""
Reproduce why parser sees garbage name/dimensions when stream starts mid-frame.

This script simulates the JS parser's first 64 + 12 bytes header parse against:
1) a valid fresh stream header
2) random midstream payload

Run:
    python unit_tester/repro_midstream_header_parse.py
"""

import os
import struct


def parse_header_like_frontend(data: bytes):
    if len(data) < 76:
        raise ValueError("Need at least 76 bytes")
    name = data[:64].decode("utf-8", errors="replace")
    _stream_id, width, height = struct.unpack(">iii", data[64:76])
    return name, width, height


def main():
    # Case A: valid stream beginning
    device_name = "SM-G960W".encode("utf-8")
    padded_name = device_name + b"\x00" * (64 - len(device_name))
    header = padded_name + struct.pack(">iii", 0, 720, 1480)
    name, width, height = parse_header_like_frontend(header + b"\x00" * 32)
    print("Case A (fresh stream):", repr(name), width, height)

    # Case B: random midstream bytes (what reconnect can hit if backend stream wasn't reset)
    midstream = os.urandom(76)
    name2, width2, height2 = parse_header_like_frontend(midstream)
    print("Case B (midstream bytes):", repr(name2), width2, height2)
    print("Expected: often unreadable name and nonsensical dimensions.")


if __name__ == "__main__":
    main()

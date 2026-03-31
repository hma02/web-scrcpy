#!/usr/bin/env python3
"""Small helper to detect likely audio bytes on a stream expected to be H.264 video."""


def detect_wrong_stream_type(chunk: bytes):
    head = chunk[:24]
    head_hex = " ".join(f"{b:02x}" for b in head)
    head_ascii = "".join(chr(b) if 32 <= b <= 126 else "." for b in head)
    has_opus = b"OpusHead" in chunk[:128]
    looks_h264_start = b"\x00\x00\x00\x01" in chunk[:128]
    return {
        "head_hex": head_hex,
        "head_ascii": head_ascii,
        "has_opus": has_opus,
        "looks_h264_start": looks_h264_start,
        "likely_wrong_socket_binding": has_opus and not looks_h264_start,
    }


def main():
    good_video_like = b"\x00\x00\x00\x01\x67\x64\x00\x1f" + b"\x00" * 32
    bad_audio_like = b"\x80\x00\x00\x00\x13OpusHead\x01\x02" + b"\x00" * 32

    for label, sample in (("good_video_like", good_video_like), ("bad_audio_like", bad_audio_like)):
        result = detect_wrong_stream_type(sample)
        print(f"\\n[{label}]")
        for k, v in result.items():
            print(f"{k}: {v}")


if __name__ == "__main__":
    main()

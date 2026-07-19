#!/usr/bin/env python3
"""Range-extract the bounded event-table member from the 60 GB ZIP64 archive."""

from __future__ import annotations

import json
import struct
import urllib.request
import zlib
from pathlib import Path


URL = (
    "https://zenodo.org/api/records/7274803/files/"
    "dopamine-reinforces-spontaneous-behavior.zip/content"
)
CENTRAL_DIRECTORY_OFFSET = 60_751_703_630
CENTRAL_DIRECTORY_SIZE = 9_670
TARGET = "dlight_raw_data/3s-pulsed-stim-dataframe.parquet"
ROOT = Path(__file__).resolve().parents[1]
PROBLEM = ROOT / "problems_complete" / "s41586-022-05611-2_spontaneous-behavior"


def range_read(start: int, end: int) -> bytes:
    request = urllib.request.Request(
        URL,
        headers={"Range": f"bytes={start}-{end}", "User-Agent": "paper-invert/1.0"},
    )
    with urllib.request.urlopen(request, timeout=600) as response:
        return response.read()


def zip64_values(
    extra: bytes,
    uncompressed32: int,
    compressed32: int,
    offset32: int,
) -> tuple[int, int, int]:
    uncompressed, compressed, offset = uncompressed32, compressed32, offset32
    index = 0
    while index + 4 <= len(extra):
        header, size = struct.unpack_from("<HH", extra, index)
        data = extra[index + 4 : index + 4 + size]
        index += 4 + size
        if header != 1:
            continue
        position = 0
        if uncompressed32 == 0xFFFFFFFF:
            uncompressed = struct.unpack_from("<Q", data, position)[0]
            position += 8
        if compressed32 == 0xFFFFFFFF:
            compressed = struct.unpack_from("<Q", data, position)[0]
            position += 8
        if offset32 == 0xFFFFFFFF:
            offset = struct.unpack_from("<Q", data, position)[0]
    return uncompressed, compressed, offset


def inventory() -> list[dict[str, int | str]]:
    central = range_read(
        CENTRAL_DIRECTORY_OFFSET,
        CENTRAL_DIRECTORY_OFFSET + CENTRAL_DIRECTORY_SIZE - 1,
    )
    entries: list[dict[str, int | str]] = []
    position = 0
    while position + 46 <= len(central) and central[position : position + 4] == b"PK\x01\x02":
        compressed32 = struct.unpack_from("<I", central, position + 20)[0]
        uncompressed32 = struct.unpack_from("<I", central, position + 24)[0]
        name_length = struct.unpack_from("<H", central, position + 28)[0]
        extra_length = struct.unpack_from("<H", central, position + 30)[0]
        comment_length = struct.unpack_from("<H", central, position + 32)[0]
        offset32 = struct.unpack_from("<I", central, position + 42)[0]
        name = central[
            position + 46 : position + 46 + name_length
        ].decode("utf-8")
        extra = central[
            position + 46 + name_length : position + 46 + name_length + extra_length
        ]
        uncompressed, compressed, offset = zip64_values(
            extra, uncompressed32, compressed32, offset32
        )
        entries.append(
            {
                "name": name,
                "compressed": compressed,
                "uncompressed": uncompressed,
                "offset": offset,
            }
        )
        position += 46 + name_length + extra_length + comment_length
    return entries


def main() -> int:
    entries = inventory()
    audit = PROBLEM / "evaluator" / "host-audit"
    audit.mkdir(parents=True, exist_ok=True)
    (audit / "zip_inventory.json").write_text(
        json.dumps(entries, indent=2) + "\n",
        encoding="utf-8",
    )
    entry = next(item for item in entries if item["name"] == TARGET)
    offset = int(entry["offset"])
    local_header = range_read(offset, offset + 4095)
    name_length, extra_length = struct.unpack_from("<HH", local_header, 26)
    method = struct.unpack_from("<H", local_header, 8)[0]
    start = offset + 30 + name_length + extra_length
    payload = range_read(start, start + int(entry["compressed"]) - 1)
    raw = zlib.decompress(payload, -15) if method == 8 else payload
    if len(raw) != int(entry["uncompressed"]):
        raise RuntimeError("Selective ZIP member size mismatch.")
    output = PROBLEM / "data" / "selective" / Path(TARGET).name
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(raw)
    print(f"Extracted {output.name}: {len(raw)} bytes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

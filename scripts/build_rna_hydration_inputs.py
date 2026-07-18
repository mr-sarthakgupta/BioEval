#!/usr/bin/env python3
"""Create blinded half-map metadata and a polymer-only pre-footprint scaffold."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import struct
import tempfile
from pathlib import Path


PROBLEM_ID = "s41586-025-08855-w_rna-hydration"
MAPS = (
    ("map_a", "1", "map_a_half_1.map.gz", 62_316_639, "EMD-42498"),
    ("map_a", "2", "map_a_half_2.map.gz", 62_317_687, "EMD-42498"),
    ("map_b", "1", "map_b_half_1.map.gz", 62_332_121, "EMD-42499"),
    ("map_b", "2", "map_b_half_2.map.gz", 62_347_914, "EMD-42499"),
)
SOURCE_MAP_SHA256 = {
    "map_a_half_1.map.gz": "760d346e654928ee31a215b1a2477d3068b32e4be9453b015cc3f10c3b03a1fa",
    "map_a_half_2.map.gz": "2f7ba5d2c771c268af26a68bb91c6cf54fcf76500ce5f607b8fb01dcfbe306b7",
    "map_b_half_1.map.gz": "d009db3dafaec0004b392ee6c5443ebbb347c6b1e40c809a5d0298f4616569bc",
    "map_b_half_2.map.gz": "43e80a8a2832580550168a294af8e386e0a265b146bb04b71e8a7385eb855218",
}
def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sanitize_mrc_gzip(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=destination.parent, suffix=".map.gz", delete=False
    ) as temporary:
        temporary_path = Path(temporary.name)
    try:
        import gzip

        with gzip.open(source, "rb") as input_handle:
            header = bytearray(input_handle.read(1024))
            if len(header) != 1024 or header[208:212] != b"MAP ":
                raise SystemExit(f"{source}: invalid or unsupported MRC header.")
            header[220:224] = struct.pack("<i", 0)
            header[224:1024] = b" " * 800
            with temporary_path.open("wb") as raw_output:
                with gzip.GzipFile(
                    fileobj=raw_output,
                    mode="wb",
                    compresslevel=6,
                    mtime=0,
                ) as output_handle:
                    output_handle.write(header)
                    shutil.copyfileobj(input_handle, output_handle, 1024 * 1024)
        temporary_path.replace(destination)
    finally:
        temporary_path.unlink(missing_ok=True)


def mrc_geometry(path: Path) -> dict[str, object]:
    import gzip

    with gzip.open(path, "rb") as handle:
        header = handle.read(1024)
    nx, ny, nz, mode = struct.unpack_from("<4i", header, 0)
    starts = struct.unpack_from("<3i", header, 16)
    mx, my, mz = struct.unpack_from("<3i", header, 28)
    cell = struct.unpack_from("<3f", header, 40)
    axes = struct.unpack_from("<3i", header, 64)
    origin = struct.unpack_from("<3f", header, 196)
    return {
        "grid_x": nx,
        "grid_y": ny,
        "grid_z": nz,
        "mode": mode,
        "start_column": starts[0],
        "start_row": starts[1],
        "start_section": starts[2],
        "mapc": axes[0],
        "mapr": axes[1],
        "maps": axes[2],
        "origin_x": f"{origin[0]:.8g}",
        "origin_y": f"{origin[1]:.8g}",
        "origin_z": f"{origin[2]:.8g}",
        "voxel_x": f"{cell[0] / mx:.8g}",
        "voxel_y": f"{cell[1] / my:.8g}",
        "voxel_z": f"{cell[2] / mz:.8g}",
    }


def build(
    problem_root: Path,
    source_pdb: Path,
    source_half_maps: Path,
) -> None:
    half_maps = problem_root / "data" / "half-maps"
    curated = problem_root / "curated"
    curated.mkdir(parents=True, exist_ok=True)

    scaffold = curated / "rna_scaffold.pdb"
    atom_count = 0
    with source_pdb.open(encoding="utf-8") as source, scaffold.open(
        "w", encoding="utf-8", newline="\n"
    ) as output:
        output.write("REMARK 1 POLYMER-ONLY PRE-FOOTPRINT RNA REFERENCE\n")
        for line in source:
            if not line.startswith("ATOM  "):
                continue
            output.write(line.rstrip("\n") + "\n")
            atom_count += 1
        output.write("END\n")
    if atom_count < 1000:
        raise SystemExit("Polymer-only scaffold contains too few atoms.")

    manifest_path = curated / "map_manifest.csv"
    hidden_sources: list[dict[str, object]] = []
    with manifest_path.open("w", newline="", encoding="utf-8") as handle:
        fields = (
            "map_blind_id",
            "half_id",
            "filename",
            "bytes",
            "sha256",
            "grid_x",
            "grid_y",
            "grid_z",
            "mode",
            "start_column",
            "start_row",
            "start_section",
            "mapc",
            "mapr",
            "maps",
            "origin_x",
            "origin_y",
            "origin_z",
            "voxel_x",
            "voxel_y",
            "voxel_z",
        )
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for blind_id, half_id, filename, expected_bytes, accession in MAPS:
            source_path = source_half_maps / filename
            if source_path.stat().st_size != expected_bytes:
                raise SystemExit(
                    f"{filename}: expected {expected_bytes} source bytes, "
                    f"got {source_path.stat().st_size}."
                )
            source_checksum = sha256(source_path)
            if source_checksum != SOURCE_MAP_SHA256[filename]:
                raise SystemExit(f"{filename}: source SHA-256 does not match the pin.")
            path = half_maps / filename
            sanitize_mrc_gzip(source_path, path)
            checksum = sha256(path)
            geometry = mrc_geometry(path)
            writer.writerow(
                {
                    "map_blind_id": blind_id,
                    "half_id": half_id,
                    "filename": filename,
                    "bytes": path.stat().st_size,
                    "sha256": checksum,
                    **geometry,
                }
            )
            hidden_sources.append(
                {
                    "map_blind_id": blind_id,
                    "half_id": half_id,
                    "source_accession": accession,
                    "source_filename": filename.replace("map_a", "emd_42498").replace(
                        "map_b", "emd_42499"
                    ),
                    "source_bytes": expected_bytes,
                    "source_sha256": source_checksum,
                    "output_bytes": path.stat().st_size,
                    "output_sha256": checksum,
                }
            )
    source_manifest = {
        "license": "CC0",
        "target_footprint_date": "2024-06-16",
        "half_maps": hidden_sources,
        "polymer_reference": {
            "source_accession": "7EZ0",
            "source_release": "2021-08-25",
            "source_sha256": sha256(source_pdb),
            "output_atoms": atom_count,
            "output_sha256": sha256(scaffold),
        },
        "scientific_evaluator": "recomputes local density directly from each sanitized half-map",
    }
    (curated / "source_manifest.json").write_text(
        json.dumps(source_manifest, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-pdb", type=Path, default=Path("/tmp/7EZ0.pdb"))
    parser.add_argument("--source-half-maps", type=Path, default=None)
    args = parser.parse_args()
    problem_root = root / "problems_imcomplete" / PROBLEM_ID
    build(
        problem_root,
        args.source_pdb.resolve(),
        (
            args.source_half_maps.resolve()
            if args.source_half_maps
            else problem_root / "data" / "source-half-maps"
        ),
    )


if __name__ == "__main__":
    main()

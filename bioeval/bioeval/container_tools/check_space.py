#!/usr/bin/env python3
"""Report workspace disk usage against the configured budget.

Exits non-zero when usage is over budget so the UEA gets a clear, scriptable signal
that it must subset data, stream files, or delete intermediates.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

WORKSPACE = Path("/workspace")
DATA = Path("/workspace/data")


def dir_size_bytes(root: Path, *, skip: Path | None = None) -> int:
    total = 0
    for dirpath, _dirnames, filenames in os.walk(root):
        p = Path(dirpath)
        if skip and (p == skip or skip in p.parents):
            continue
        for name in filenames:
            fp = p / name
            try:
                if fp.is_symlink():
                    continue
                total += fp.stat().st_size
            except OSError:
                pass
    return total


def main() -> int:
    budget_gb = float(os.getenv("BIOEVAL_DISK_BUDGET_GB", "20"))
    budget_bytes = budget_gb * 1024**3

    usage = shutil.disk_usage(str(WORKSPACE))
    workspace_used = dir_size_bytes(WORKSPACE, skip=DATA)
    data_used = dir_size_bytes(DATA) if DATA.exists() else 0

    gib = 1024**3
    print(f"Disk budget:        {budget_gb:.1f} GiB")
    print(f"Workspace scratch:  {workspace_used / gib:.2f} GiB (counts against budget)")
    print(f"Granted data (ro):  {data_used / gib:.2f} GiB")
    print(f"Filesystem free:    {usage.free / gib:.2f} GiB")

    remaining = budget_bytes - workspace_used
    if remaining < 0:
        print(
            f"OVER BUDGET by {abs(remaining) / gib:.2f} GiB. Delete intermediates, "
            "subset large datasets (ask the data-agent for fewer rows/columns), or "
            "stream files instead of materializing them."
        )
        return 1
    print(f"Remaining budget:   {remaining / gib:.2f} GiB")
    if remaining < 2 * gib:
        print("WARNING: low remaining budget. Prefer subsets and clean up intermediates.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

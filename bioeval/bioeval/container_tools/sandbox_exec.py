#!/usr/bin/env python3
"""Execute one analysis command inside a fail-closed Landlock filesystem sandbox."""

from __future__ import annotations

import ctypes
import os
import platform
import sys
from pathlib import Path


LANDLOCK_CREATE_RULESET_VERSION = 1
LANDLOCK_RULE_PATH_BENEATH = 1
PR_SET_NO_NEW_PRIVS = 38

ACCESS_EXECUTE = 1 << 0
ACCESS_WRITE_FILE = 1 << 1
ACCESS_READ_FILE = 1 << 2
ACCESS_READ_DIR = 1 << 3
ACCESS_REMOVE_DIR = 1 << 4
ACCESS_REMOVE_FILE = 1 << 5
ACCESS_MAKE_CHAR = 1 << 6
ACCESS_MAKE_DIR = 1 << 7
ACCESS_MAKE_REG = 1 << 8
ACCESS_MAKE_SOCK = 1 << 9
ACCESS_MAKE_FIFO = 1 << 10
ACCESS_MAKE_BLOCK = 1 << 11
ACCESS_MAKE_SYM = 1 << 12

READ = ACCESS_READ_FILE | ACCESS_READ_DIR
WRITE = (
    ACCESS_WRITE_FILE
    | ACCESS_REMOVE_DIR
    | ACCESS_REMOVE_FILE
    | ACCESS_MAKE_CHAR
    | ACCESS_MAKE_DIR
    | ACCESS_MAKE_REG
    | ACCESS_MAKE_SOCK
    | ACCESS_MAKE_FIFO
    | ACCESS_MAKE_BLOCK
    | ACCESS_MAKE_SYM
)
HANDLED_ACCESS = ACCESS_EXECUTE | READ | WRITE


class RulesetAttr(ctypes.Structure):
    _fields_ = [("handled_access_fs", ctypes.c_uint64)]


class PathBeneathAttr(ctypes.Structure):
    _fields_ = [
        ("allowed_access", ctypes.c_uint64),
        ("parent_fd", ctypes.c_int),
        ("reserved", ctypes.c_uint32),
    ]


def _syscall_numbers() -> tuple[int, int, int]:
    machine = platform.machine().lower()
    if machine in {"x86_64", "amd64"}:
        return 444, 445, 446
    if machine in {"aarch64", "arm64"}:
        return 444, 445, 446
    raise RuntimeError(f"Landlock syscall numbers are unknown for {machine!r}")


def _add_path_rule(
    libc: ctypes.CDLL,
    add_rule_nr: int,
    ruleset_fd: int,
    path: Path,
    access: int,
) -> None:
    if not path.exists():
        return
    path_fd = os.open(path, os.O_PATH | os.O_CLOEXEC)
    try:
        attr = PathBeneathAttr(access, path_fd, 0)
        if libc.syscall(
            add_rule_nr,
            ruleset_fd,
            LANDLOCK_RULE_PATH_BENEATH,
            ctypes.byref(attr),
            0,
        ) != 0:
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error), str(path))
    finally:
        os.close(path_fd)


def apply_filesystem_sandbox(workspace: Path) -> None:
    """Allow system reads/execs and workspace reads/writes; deny every other path."""
    create_ruleset_nr, add_rule_nr, restrict_self_nr = _syscall_numbers()
    libc = ctypes.CDLL(None, use_errno=True)

    abi = libc.syscall(
        create_ruleset_nr,
        0,
        0,
        LANDLOCK_CREATE_RULESET_VERSION,
    )
    if abi < 1:
        error = ctypes.get_errno()
        raise RuntimeError(
            f"Landlock is required for run_command isolation (ABI query failed: "
            f"{os.strerror(error) if error else abi})"
        )

    ruleset_attr = RulesetAttr(HANDLED_ACCESS)
    ruleset_fd = libc.syscall(
        create_ruleset_nr,
        ctypes.byref(ruleset_attr),
        ctypes.sizeof(ruleset_attr),
        0,
    )
    if ruleset_fd < 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))

    try:
        # Runtime and scientific packages may be read/executed, but never modified.
        for path in ("/usr", "/bin", "/lib", "/lib64"):
            _add_path_rule(
                libc,
                add_rule_nr,
                ruleset_fd,
                Path(path),
                READ | ACCESS_EXECUTE,
            )
        # Basic runtime configuration is readable. Sensitive homes, /proc, /run,
        # /submit, and /logs deliberately receive no rule.
        _add_path_rule(libc, add_rule_nr, ruleset_fd, Path("/etc"), READ)
        for path in ("/dev/null", "/dev/urandom", "/dev/random"):
            _add_path_rule(libc, add_rule_nr, ruleset_fd, Path(path), ACCESS_READ_FILE)

        workspace.mkdir(parents=True, exist_ok=True)
        _add_path_rule(libc, add_rule_nr, ruleset_fd, workspace, READ | WRITE)

        if libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error))
        if libc.syscall(restrict_self_nr, ruleset_fd, 0) != 0:
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error))
    finally:
        os.close(ruleset_fd)


def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit("sandbox_exec requires a command")
    workspace = Path(os.getenv("BIOEVAL_WORKSPACE", "/workspace")).resolve()
    try:
        apply_filesystem_sandbox(workspace)
    except Exception as exc:
        print(f"run_command sandbox unavailable: {exc}", file=sys.stderr)
        return 126
    os.chdir(workspace)
    os.execvpe(sys.argv[1], sys.argv[1:], os.environ)
    return 127


if __name__ == "__main__":
    raise SystemExit(main())

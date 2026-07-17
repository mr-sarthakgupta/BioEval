#!/usr/bin/env python3
"""Run analysis Python while denying network and child-process escape paths."""

from __future__ import annotations

import ctypes
import errno
import runpy
import os
import sys
from pathlib import Path


BLOCKED_AUDIT_PREFIXES = (
    "socket.",
    "subprocess.",
)
BLOCKED_AUDIT_EVENTS = {
    "os.fork",
    "os.forkpty",
    "os.exec",
    "os.posix_spawn",
    "os.spawn",
    "os.system",
}
WORKSPACE = Path(os.getenv("BIOEVAL_WORKSPACE", "/workspace")).resolve()
SYSTEM_READ_ROOTS = tuple(
    Path(path).resolve()
    for path in (
        "/usr",
        "/bin",
        "/lib",
        "/lib64",
        "/etc",
        sys.prefix,
        sys.base_prefix,
    )
    if Path(path).exists()
)

SCMP_ACT_ALLOW = 0x7FFF0000
SCMP_ACT_ERRNO = 0x00050000
SCMP_CMP_MASKED_EQ = 7
CLONE_THREAD = 0x00010000
BLOCKED_SYSCALLS = (
    "socket",
    "socketpair",
    "connect",
    "bind",
    "listen",
    "accept",
    "accept4",
    "sendto",
    "sendmsg",
    "sendmmsg",
    "recvfrom",
    "recvmsg",
    "recvmmsg",
    "shutdown",
    "fork",
    "vfork",
    "execve",
    "execveat",
    "ptrace",
    "process_vm_readv",
    "process_vm_writev",
    "mount",
    "umount2",
    "pivot_root",
    "chroot",
    "setns",
    "unshare",
    "bpf",
    "keyctl",
    "add_key",
    "request_key",
    "userfaultfd",
)


class ScmpArgCmp(ctypes.Structure):
    _fields_ = [
        ("arg", ctypes.c_uint),
        ("op", ctypes.c_uint),
        ("datum_a", ctypes.c_uint64),
        ("datum_b", ctypes.c_uint64),
    ]


def install_seccomp_filter() -> None:
    """Kernel-enforce no network, child process, namespace, or tracing syscalls."""
    try:
        seccomp = ctypes.CDLL("libseccomp.so.2", use_errno=True)
    except OSError as exc:
        raise RuntimeError("libseccomp is required for restricted Python") from exc
    seccomp.seccomp_init.argtypes = [ctypes.c_uint32]
    seccomp.seccomp_init.restype = ctypes.c_void_p
    seccomp.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    seccomp.seccomp_syscall_resolve_name.restype = ctypes.c_int
    seccomp.seccomp_rule_add.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_int,
        ctypes.c_uint,
    ]
    seccomp.seccomp_rule_add.restype = ctypes.c_int
    seccomp.seccomp_rule_add_array.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_int,
        ctypes.c_uint,
        ctypes.POINTER(ScmpArgCmp),
    ]
    seccomp.seccomp_rule_add_array.restype = ctypes.c_int
    seccomp.seccomp_load.argtypes = [ctypes.c_void_p]
    seccomp.seccomp_load.restype = ctypes.c_int
    seccomp.seccomp_release.argtypes = [ctypes.c_void_p]

    context = seccomp.seccomp_init(SCMP_ACT_ALLOW)
    if not context:
        raise RuntimeError("could not initialize seccomp")
    try:
        deny = SCMP_ACT_ERRNO | errno.EPERM
        for name in BLOCKED_SYSCALLS:
            number = seccomp.seccomp_syscall_resolve_name(name.encode())
            if number < 0:
                continue
            result = seccomp.seccomp_rule_add(context, deny, number, 0)
            if result != 0:
                raise OSError(-result, os.strerror(-result))
        clone_number = seccomp.seccomp_syscall_resolve_name(b"clone")
        if clone_number >= 0:
            # pthreads use CLONE_THREAD and remain available to NumPy/BLAS. A
            # clone without CLONE_THREAD creates a child process and is denied.
            comparison = ScmpArgCmp(0, SCMP_CMP_MASKED_EQ, CLONE_THREAD, 0)
            result = seccomp.seccomp_rule_add_array(
                context,
                deny,
                clone_number,
                1,
                ctypes.byref(comparison),
            )
            if result != 0:
                raise OSError(-result, os.strerror(-result))
        clone3_number = seccomp.seccomp_syscall_resolve_name(b"clone3")
        if clone3_number >= 0:
            # clone3 stores flags behind a pointer, which classic seccomp cannot
            # inspect. Report it as unavailable so libc falls back to clone,
            # where the CLONE_THREAD flag can be filtered safely above.
            result = seccomp.seccomp_rule_add(
                context,
                SCMP_ACT_ERRNO | errno.ENOSYS,
                clone3_number,
                0,
            )
            if result != 0:
                raise OSError(-result, os.strerror(-result))
        result = seccomp.seccomp_load(context)
        if result != 0:
            raise OSError(-result, os.strerror(-result))
    finally:
        seccomp.seccomp_release(context)


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _check_open(args: tuple[object, ...]) -> None:
    if not args or isinstance(args[0], int):
        return
    raw_path = os.fspath(args[0])
    path = Path(raw_path)
    if not path.is_absolute():
        path = Path.cwd() / path
    resolved = path.resolve()
    mode = args[1] if len(args) > 1 else None
    flags = args[2] if len(args) > 2 and isinstance(args[2], int) else 0
    write_requested = (
        (isinstance(mode, str) and any(marker in mode for marker in ("w", "a", "x", "+")))
        or flags & os.O_ACCMODE != os.O_RDONLY
        or bool(flags & (os.O_CREAT | os.O_TRUNC | os.O_APPEND))
    )
    if write_requested:
        if not _inside(resolved, WORKSPACE):
            raise PermissionError("Analysis Python may only write inside /workspace.")
        return
    readable = _inside(resolved, WORKSPACE) or any(
        _inside(resolved, root) for root in SYSTEM_READ_ROOTS
    )
    if resolved in {Path("/dev/null"), Path("/dev/urandom"), Path("/dev/random")}:
        readable = True
    if not readable:
        raise PermissionError("Analysis Python may only read workspace and runtime files.")


def deny_unsafe_runtime(event: str, _args: tuple[object, ...]) -> None:
    if event == "open":
        _check_open(_args)
        return
    if event in BLOCKED_AUDIT_EVENTS or event.startswith(BLOCKED_AUDIT_PREFIXES):
        raise PermissionError(
            "Network and child-process access are disabled in analysis Python; "
            "use the guarded research tools."
        )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        raise SystemExit("restricted Python requires -c, -m, or a script path")
    install_seccomp_filter()
    sys.addaudithook(deny_unsafe_runtime)
    if args[0] == "-c":
        if len(args) < 2:
            raise SystemExit("-c requires code")
        sys.argv = ["-c", *args[2:]]
        namespace = {"__name__": "__main__", "__file__": "<string>"}
        exec(compile(args[1], "<string>", "exec"), namespace, namespace)
        return 0
    if args[0] == "-m":
        if len(args) < 2:
            raise SystemExit("-m requires a module")
        sys.argv = [args[1], *args[2:]]
        runpy.run_module(args[1], run_name="__main__", alter_sys=True)
        return 0
    sys.argv = [args[0], *args[1:]]
    runpy.run_path(args[0], run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

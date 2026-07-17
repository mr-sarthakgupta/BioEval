from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


TOOLS = Path(__file__).parents[1] / "bioeval" / "container_tools"
sys.path.insert(0, str(TOOLS))

from run_command import safety_error, sandbox_environment  # noqa: E402


class RunCommandSandboxTests(unittest.TestCase):
    def test_execution_capable_utilities_are_not_allowed(self) -> None:
        for command in (
            """awk 'BEGIN{system("id")}'""",
            "find . -exec id ;",
            "sed -n 1e /etc/passwd",
            "Rscript analysis.R",
            "env",
            "rg --pre id needle .",
            "sort --compress-program=id data.csv",
        ):
            with self.subTest(command=command):
                self.assertIsNotNone(safety_error(command))

    def test_embedded_python_paths_are_stopped_by_restricted_runtime(self) -> None:
        runner = TOOLS / "restricted_python.py"
        result = subprocess.run(
            [
                sys.executable,
                str(runner),
                "-c",
                """print(open("/pro" + "c/self/environ").read())""",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("may only read workspace", result.stderr)

    def test_raw_syscall_network_and_process_bypasses_are_blocked(self) -> None:
        runner = TOOLS / "restricted_python.py"
        code = """
import ctypes
libc = ctypes.CDLL(None)
socket_call = getattr(libc, "so" + "cket")
system_call = getattr(libc, "sys" + "tem")
assert socket_call(2, 1, 0) == -1
assert system_call(b"id") != 0
"""
        result = subprocess.run(
            [sys.executable, str(runner), "-c", code],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_threads_remain_available_for_scientific_libraries(self) -> None:
        runner = TOOLS / "restricted_python.py"
        code = """
import threading
completed = []
thread = threading.Thread(target=lambda: completed.append(True))
thread.start()
thread.join()
assert completed == [True]
"""
        result = subprocess.run(
            [sys.executable, str(runner), "-c", code],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_child_environment_drops_credentials(self) -> None:
        with patch.dict(
            os.environ,
            {
                "AWS_SECRET_ACCESS_KEY": "secret",
                "AWS_SESSION_TOKEN": "token",
                "OPENAI_API_KEY": "key",
            },
        ):
            child = sandbox_environment()
        self.assertNotIn("AWS_SECRET_ACCESS_KEY", child)
        self.assertNotIn("AWS_SESSION_TOKEN", child)
        self.assertNotIn("OPENAI_API_KEY", child)

    def test_landlock_denies_files_outside_workspace(self) -> None:
        sandbox = TOOLS / "sandbox_exec.py"
        sandboxed_python = "/usr/bin/python3"
        with tempfile.TemporaryDirectory() as tmp:
            env = {
                "PATH": "/usr/local/bin:/usr/bin:/bin",
                "BIOEVAL_WORKSPACE": tmp,
                "HOME": tmp,
            }
            denied = subprocess.run(
                [
                    sys.executable,
                    str(sandbox),
                    sandboxed_python,
                    "-c",
                    """open("/proc/self/environ").read()""",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                env=env,
            )
            self.assertNotEqual(denied.returncode, 0)

            allowed = subprocess.run(
                [
                    sys.executable,
                    str(sandbox),
                    sandboxed_python,
                    "-c",
                    """open("analysis.txt", "w").write("ok")""",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                env=env,
            )
            self.assertEqual(allowed.returncode, 0, allowed.stderr)
            self.assertEqual((Path(tmp) / "analysis.txt").read_text(), "ok")


if __name__ == "__main__":
    unittest.main()

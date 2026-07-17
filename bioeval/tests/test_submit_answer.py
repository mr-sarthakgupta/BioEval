from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bioeval.container_tools.submit_answer import main


class SubmitAnswerTests(unittest.TestCase):
    def test_manifest_artifacts_are_copied_and_hashed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "workspace"
            workspace.mkdir()
            transcript = workspace / "transcript.md"
            transcript.write_text("analysis transcript")
            artifact = workspace / "result.csv"
            artifact.write_text("metric,value\ncorrelation,0.82\n")
            manifest = workspace / "analysis_manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "artifacts": [
                            {
                                "path": "result.csv",
                                "description": "Held-out metric output",
                            }
                        ]
                    }
                )
            )
            submit_dir = root / "submit"

            with (
                patch.dict(
                    "os.environ",
                    {
                        "BIOEVAL_WORKSPACE_ROOT": str(workspace),
                        "BIOEVAL_TOOL_LOG": str(root / "tool_calls.jsonl"),
                    },
                    clear=False,
                ),
                patch(
                    "sys.argv",
                    [
                        "submit_answer",
                        "--text",
                        "Final answer",
                        "--transcript",
                        str(transcript),
                        "--analysis-manifest",
                        str(manifest),
                        "--submit-dir",
                        str(submit_dir),
                    ],
                ),
            ):
                exit_code = main()

            self.assertEqual(exit_code, 0)
            submitted = json.loads((submit_dir / "analysis_manifest.json").read_text())
            row = submitted["artifacts"][0]
            self.assertEqual(row["path"], "artifacts/artifact_001.csv")
            self.assertEqual(len(row["sha256"]), 64)
            self.assertTrue((submit_dir / row["path"]).is_file())


if __name__ == "__main__":
    unittest.main()

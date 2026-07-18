from __future__ import annotations

import bz2
import gzip
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from bioeval.curation import select_instructions_by_keywords
from bioeval.data_agent import _identifiers_for, make_plan
from bioeval.guard import scan_file
from bioeval.providers import (
    _PinnedHTTPSConnection,
    _safe_destination,
    _validate_public_url,
)
from bioeval.search_proxy import (
    OPENALEX_DOI_ID_CACHE,
    OPENALEX_GRAPH_CACHE,
    _after_external_cutoff,
    _page_publication_date,
    build_openalex_blocked_graph,
    openalex_graph_blocks,
    paper_matches_hidden_work,
    restricted_fetch_webpage,
)
from bioeval.schemas import CatalogEntry, DataCatalog, DatasetRequest


class GuardrailHardeningTests(unittest.TestCase):
    def setUp(self) -> None:
        OPENALEX_GRAPH_CACHE.clear()
        OPENALEX_DOI_ID_CACHE.clear()

    def test_structured_matcher_outage_fails_closed(self) -> None:
        request = DatasetRequest(
            question="Drosophila survival assay",
            structured_experiment=True,
        )
        catalog = DataCatalog(problem_id="test", entries=[])
        with patch("bioeval.data_agent.opencode_runner.plan_with_bedrock", return_value=None):
            plan = make_plan(catalog, request, "model", "bedrock:us-east-1")
        self.assertTrue(plan.deny)
        self.assertEqual(plan.instructions, [])

    def test_keyword_fallback_never_selects_zero_overlap_entry(self) -> None:
        catalog = DataCatalog(
            problem_id="test",
            entries=[
                CatalogEntry(
                    id="butterfly_survival",
                    description="Butterfly adult survival observations",
                    source_paths=["survival.csv"],
                )
            ],
        )
        request = DatasetRequest(question="quantum magnetometer calibration")
        self.assertEqual(select_instructions_by_keywords(catalog, request), [])

    def test_hidden_identifier_load_failure_is_fail_closed(self) -> None:
        with patch(
            "bioeval.data_agent.load_problem_spec",
            side_effect=FileNotFoundError("missing"),
        ):
            with self.assertRaises(RuntimeError):
                _identifiers_for("missing-problem")

    def test_large_file_marker_in_middle_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "measurements.csv"
            marker = b"held-out-paper-marker"
            path.write_bytes(b"a" * 4_000_000 + marker + b"b" * 4_000_000)
            self.assertIsNotNone(scan_file(path, [marker.decode()]))

    def test_standalone_gzip_marker_is_detected_after_decompression(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "blinded.map.gz"
            with gzip.open(path, "wb") as handle:
                handle.write(b"\x00" * 512 + b"EMD-42498" + b"\x00" * 512)
            self.assertIsNotNone(scan_file(path, ["EMD-42498"]))

    def test_hidden_and_extensionless_files_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for name in (".env", "analysis"):
                path = Path(tmp) / name
                path.write_text("apparently harmless")
                self.assertIsNotNone(scan_file(path, []), name)

    def test_bzip2_and_nested_compression_are_rejected_or_scanned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            compressed = root / "measurements.csv.bz2"
            with bz2.open(compressed, "wb") as handle:
                handle.write(b"held-out-paper-marker")
            self.assertIsNotNone(
                scan_file(compressed, ["held-out-paper-marker"])
            )

            nested = root / "measurements.zip"
            payload = gzip.compress(b"held-out-paper-marker")
            with zipfile.ZipFile(nested, "w") as archive:
                archive.writestr("nested.csv.gz", payload)
            self.assertIsNotNone(
                scan_file(nested, ["held-out-paper-marker"])
            )

    def test_common_statistics_worksheet_name_is_not_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "measurements.xlsx"
            workbook = (
                '<?xml version="1.0" encoding="UTF-8"?>'
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                '<sheets><sheet name="statistics" sheetId="1"/></sheets></workbook>'
            )
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("xl/workbook.xml", workbook)
            self.assertIsNone(scan_file(path, []))

    def test_provider_paths_and_private_hosts_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                _safe_destination(Path(tmp), "../escape.csv")
        with self.assertRaises(ValueError):
            _validate_public_url("https://127.0.0.1/private")

    def test_web_fetch_rejects_private_target_before_request(self) -> None:
        result = restricted_fetch_webpage(
            url="https://127.0.0.1/private",
            max_chars=1000,
            identifiers=[],
        )
        self.assertEqual(result["status"], "denied")

    def test_provider_connection_uses_only_pinned_address(self) -> None:
        connection = _PinnedHTTPSConnection(
            "public.example",
            pinned_addresses=("93.184.216.34",),
            timeout=5,
        )
        raw_socket = MagicMock()
        wrapped_socket = MagicMock()
        connection._context = MagicMock()
        connection._context.wrap_socket.return_value = wrapped_socket
        with patch(
            "bioeval.providers.socket.create_connection",
            return_value=raw_socket,
        ) as create_connection:
            connection.connect()
        create_connection.assert_called_once_with(
            ("93.184.216.34", 443),
            5,
            None,
        )
        connection._context.wrap_socket.assert_called_once_with(
            raw_socket,
            server_hostname="public.example",
        )

    def test_external_cutoff_rejects_new_or_undated_records(self) -> None:
        cutoff = "2020-06-01T00:00:00Z"
        self.assertTrue(
            _after_external_cutoff({"publicationDate": "2020-06-02"}, cutoff)
        )
        self.assertFalse(
            _after_external_cutoff({"publicationDate": "2020-05-31"}, cutoff)
        )
        self.assertTrue(_after_external_cutoff({"title": "undated"}, cutoff))
        self.assertEqual(
            _page_publication_date(
                '<meta property="article:published_time" content="2019-03-04">',
                {},
            ),
            "2019-03-04",
        )

    def test_incomplete_openalex_graph_fails_closed(self) -> None:
        with patch(
            "bioeval.search_proxy.build_openalex_blocked_graph",
            return_value=(frozenset(), False),
        ):
            self.assertTrue(
                openalex_graph_blocks(
                    "https://openalex.org/W999",
                    ["10.1234/held-out"],
                )
            )

    def test_ambiguous_document_formats_are_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("metadata.json", "export.bib", "page.html", "legacy.xls"):
                path = Path(tmp) / name
                path.write_text("apparently harmless")
                self.assertIsNotNone(scan_file(path, []), name)

    def test_restricted_python_blocks_socket_creation(self) -> None:
        runner = (
            Path(__file__).parents[1]
            / "bioeval"
            / "container_tools"
            / "restricted_python.py"
        )
        result = subprocess.run(
            [sys.executable, str(runner), "-c", "import socket; socket.socket()"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("disabled in analysis Python", result.stderr)

    def test_openalex_graph_blocks_multihop_descendants(self) -> None:
        def fake_get(_path: str, params: dict, **_kwargs):
            graph = {
                "doi:10.1234/held-out": ["https://openalex.org/W1"],
                "cites:W1": ["https://openalex.org/W2"],
                "cites:W2": ["https://openalex.org/W3"],
                "cites:W3": [],
            }
            results = [{"id": item} for item in graph.get(params["filter"], [])]
            return {"results": results, "meta": {"next_cursor": None}}, None

        identifiers = ["10.1234/held-out", "Held-out paper title"]
        with (
            patch("bioeval.search_proxy.openalex_get", side_effect=fake_get),
            patch.dict(
                "os.environ",
                {
                    "BIOEVAL_OPENALEX_DESCENDANT_DEPTH": "20",
                    "BIOEVAL_OPENALEX_DESCENDANT_MAX_NODES": "100",
                },
            ),
        ):
            blocked, complete = build_openalex_blocked_graph(identifiers)
            self.assertTrue(complete)
            self.assertEqual(blocked, frozenset({"W1", "W2", "W3"}))
            self.assertTrue(openalex_graph_blocks("https://openalex.org/W3", identifiers))
            self.assertTrue(
                paper_matches_hidden_work(
                    {"openalexId": "W3", "externalIds": {}},
                    identifiers,
                )
            )
            self.assertFalse(openalex_graph_blocks("https://openalex.org/W99", identifiers))


if __name__ == "__main__":
    unittest.main()

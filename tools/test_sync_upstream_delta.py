#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 The TotalDrop Contributors
# SPDX-License-Identifier: MIT OR Apache-2.0
"""Unit tests for `sync_upstream_delta.py`."""

from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sync_upstream_delta as sud  # noqa: E402


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


class SyncUpstreamDeltaTests(unittest.TestCase):
    def test_core_crate_maps_to_expected_modules(self) -> None:
        targets = dict(sud.map_upstream_path("crates/totaldrop-proto/src/lib.rs"))
        self.assertEqual(targets["00-core"], "crates/totaldrop-proto/src/lib.rs")
        self.assertEqual(targets["02-servers"], "crates/totaldrop-proto/src/lib.rs")
        self.assertEqual(targets["06-windows"], "crates/totaldrop-proto/src/lib.rs")
        self.assertEqual(targets["10-web-wasm"], "crates/totaldrop-proto/src/lib.rs")
        self.assertNotIn("03-site", targets)

    def test_site_and_server_exact_and_prefix_mappings(self) -> None:
        self.assertEqual(
            sud.map_upstream_path("server/rendezvous-worker/src/index.ts"),
            [("02-servers", "cloudflare-rendezvous/src/index.ts")],
        )
        self.assertEqual(
            sud.map_upstream_path("site/public/index.html"),
            [("03-site", "public/index.html")],
        )
        l10n_status = dict(sud.map_upstream_path("l10n/status.json"))
        self.assertEqual(l10n_status["03-site"], "vendor/l10n/status.json")
        self.assertEqual(l10n_status["00-core"], "l10n/status.json")

    def test_protected_standalone_relpaths_are_excluded(self) -> None:
        linux_desktop = dict(sud.map_upstream_path("linux/src/desktop.rs"))
        self.assertNotIn("04-linux", linux_desktop)

    def test_resolve_module_dir_supports_both_local_and_github_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            gh_dir = root / "totaldrop-windows"
            gh_dir.mkdir()
            self.assertEqual(sud.resolve_module_dir(root, "06-windows"), gh_dir)

    def test_end_to_end_delta_verify_and_sync_on_temp_git_repos(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            upstream = root / "upstream"
            modules = root / "modules"
            upstream.mkdir()
            modules.mkdir()

            _git(upstream, "init", "-b", "main")
            _git(upstream, "config", "user.name", "Test")
            _git(upstream, "config", "user.email", "test@example.com")

            # Initial baseline commit in upstream
            proto_file = upstream / "crates" / "totaldrop-proto" / "src" / "wire.rs"
            site_file = upstream / "site" / "public" / "app.js"
            old_file = upstream / "site" / "public" / "legacy.js"
            proto_file.parent.mkdir(parents=True)
            site_file.parent.mkdir(parents=True)
            proto_file.write_text("// v1\n", encoding="utf-8")
            site_file.write_text("console.log('v1');\n", encoding="utf-8")
            old_file.write_text("legacy();\n", encoding="utf-8")
            _git(upstream, "add", "-A")
            _git(upstream, "commit", "-m", "baseline")
            base_sha = _git(upstream, "rev-parse", "HEAD")

            # Populate matching module folders using GitHub repository directory names
            for _, repo_name in sud.MODULE_TO_GITHUB_REPO.items():
                (modules / repo_name).mkdir()
            for rel in ("crates/totaldrop-proto/src/wire.rs", "site/public/app.js", "site/public/legacy.js"):
                for mod, dest in sud.map_upstream_path(rel):
                    dst = sud.resolve_module_dir(modules, mod) / dest
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    dst.write_bytes((upstream / rel).read_bytes())

            # Baseline verify passes
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = sud.cmd_verify(upstream, modules)
            self.assertEqual(rc, 0)
            self.assertIn("Parity OK", buf.getvalue())

            # Advance upstream with Modify + Add + Delete
            proto_file.write_text("// v2\n", encoding="utf-8")
            new_site = upstream / "site" / "public" / "new.css"
            new_site.write_text("body { margin: 0; }\n", encoding="utf-8")
            old_file.unlink()
            _git(upstream, "add", "-A")
            _git(upstream, "commit", "-m", "update")

            # Verify now detects drift before sync
            with redirect_stdout(io.StringIO()):
                self.assertEqual(sud.cmd_verify(upstream, modules), 1)

            # JSON delta lists affected GitHub repositories accurately
            delta_buf = io.StringIO()
            with redirect_stdout(delta_buf):
                self.assertEqual(sud.cmd_delta(upstream, base_sha, "HEAD", True), 0)
            payload = json.loads(delta_buf.getvalue())
            self.assertEqual(payload["changed_upstream_files"], 3)
            self.assertIn("totaldrop-core", payload["affected_repositories"])
            self.assertIn("totaldrop-site", payload["affected_repositories"])

            # Dry-run does not write changes
            with redirect_stdout(io.StringIO()):
                self.assertEqual(sud.cmd_sync(upstream, modules, base_sha, "HEAD", False), 0)
            self.assertFalse((modules / "totaldrop-site" / "public" / "new.css").exists())

            # Apply sync updates all mapped repositories and restores 100% parity
            with redirect_stdout(io.StringIO()):
                self.assertEqual(sud.cmd_sync(upstream, modules, base_sha, "HEAD", True), 0)
            self.assertTrue((modules / "totaldrop-site" / "public" / "new.css").is_file())
            self.assertFalse((modules / "totaldrop-site" / "public" / "legacy.js").exists())
            with redirect_stdout(io.StringIO()):
                self.assertEqual(sud.cmd_verify(upstream, modules), 0)


if __name__ == "__main__":
    unittest.main()

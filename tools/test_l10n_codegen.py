#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 The TotalDrop Contributors
# SPDX-License-Identifier: MIT OR Apache-2.0

"""Unit tests for `tools/l10n_codegen.py`."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import l10n_codegen

REPO_ROOT = Path(__file__).resolve().parent.parent
REAL_L10N_DIR = REPO_ROOT / "l10n"


class L10nCodegenTests(unittest.TestCase):
    def test_real_35_locale_catalog_validates_cleanly(self) -> None:
        bundle, errors = l10n_codegen.load_and_validate(REAL_L10N_DIR)
        self.assertEqual(errors, [])
        assert bundle is not None
        self.assertEqual(len(l10nn := l10n_codegen.CANONICAL_TAGS), 35)
        self.assertIn("tr", l10nn)
        self.assertTrue(bundle.is_reviewed("en"))
        self.assertTrue(bundle.is_reviewed("tr"))
        self.assertFalse(bundle.is_reviewed("ar"))
        self.assertEqual(bundle.direction("ar"), "rtl")
        self.assertEqual(bundle.direction("fa"), "rtl")
        self.assertEqual(bundle.direction("he"), "rtl")
        self.assertEqual(bundle.direction("ur"), "rtl")
        self.assertEqual(bundle.direction("tr"), "ltr")

    def test_critical_keys_fall_back_to_english_for_unreviewed_locales(self) -> None:
        bundle, errors = l10n_codegen.load_and_validate(REAL_L10N_DIR)
        self.assertEqual(errors, [])
        assert bundle is not None
        en_strings = bundle.effective_app_strings("en")
        tr_strings = bundle.effective_app_strings("tr")
        ar_strings = bundle.effective_app_strings("ar")
        # Reviewed Turkish keeps its native critical string:
        self.assertNotEqual(
            tr_strings["verificationTitle"], en_strings["verificationTitle"]
        )
        # Unreviewed Arabic falls back to English on critical security strings,
        # while keeping Arabic non-critical strings:
        self.assertEqual(
            ar_strings["verificationTitle"], en_strings["verificationTitle"]
        )
        self.assertEqual(ar_strings["receiveAccept"], en_strings["receiveAccept"])
        self.assertNotEqual(ar_strings["homeSendTitle"], en_strings["homeSendTitle"])

    def test_emits_deterministic_winui_apple_web_and_summary_bundles(self) -> None:
        bundle, errors = l10n_codegen.load_and_validate(REAL_L10N_DIR)
        self.assertEqual(errors, [])
        assert bundle is not None

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            winui_dir = tmp_path / "Strings"
            l10n_codegen.emit_winui_resw(bundle, winui_dir)
            locales_manifest = json.loads(
                (winui_dir / "locales.json").read_text(encoding="utf-8")
            )
            self.assertEqual(locales_manifest["localeCount"], 35)
            for tag in l10n_codegen.CANONICAL_TAGS:
                resw_file = winui_dir / tag / "Resources.resw"
                self.assertTrue(resw_file.is_file(), f"missing {resw_file}")
                root = ET.fromstring(resw_file.read_text(encoding="utf-8"))
                self.assertEqual(root.tag, "root")

            xcstrings_file = tmp_path / "Resources" / "Localizable.xcstrings"
            l10n_codegen.emit_apple_xcstrings(bundle, xcstrings_file)
            xc = json.loads(xcstrings_file.read_text(encoding="utf-8"))
            self.assertEqual(xc["sourceLanguage"], "en")
            self.assertEqual(xc["version"], "1.0")
            ver_locs = xc["strings"]["verificationTitle"]["localizations"]
            self.assertEqual(len(ver_locs), 35)
            self.assertEqual(
                ver_locs["ar"]["stringUnit"]["value"],
                ver_locs["en"]["stringUnit"]["value"],
            )
            self.assertEqual(ver_locs["tr"]["stringUnit"]["state"], "translated")
            self.assertEqual(
                xc["strings"]["homeSendTitle"]["localizations"]["ar"]["stringUnit"][
                    "state"
                ],
                "needs_review",
            )

            web_dir = tmp_path / "i18n"
            l10n_codegen.emit_web_json(bundle, web_dir)
            web_manifest = json.loads(
                (web_dir / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(web_manifest["localeCount"], 35)
            ar_web = json.loads((web_dir / "ar.json").read_text(encoding="utf-8"))
            self.assertEqual(ar_web["dir"], "rtl")
            self.assertFalse(ar_web["reviewed"])
            self.assertEqual(
                ar_web["strings"]["verificationTitle"],
                bundle.app_catalogs["en"]["verificationTitle"],
            )

            summary_file = tmp_path / "summary.json"
            l10n_codegen.emit_summary_json(bundle, summary_file)
            summary = json.loads(summary_file.read_text(encoding="utf-8"))
            self.assertEqual(summary["localeCount"], 35)

    def test_rejects_bidi_override_and_placeholder_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            copied = Path(tmp) / "l10n"
            shutil.copytree(REAL_L10N_DIR, copied)
            fr_path = copied / "app" / "app_fr.arb"
            fr_obj = json.loads(fr_path.read_text(encoding="utf-8"))
            fr_obj["sendShareText"] = "Bad {wrongPlaceholder} \u202Espoof"
            fr_path.write_text(
                json.dumps(fr_obj, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            bundle, errors = l10n_codegen.load_and_validate(copied)
            self.assertIsNone(bundle)
            joined = "\n".join(errors)
            self.assertIn("forbidden control/bidi char U+202E", joined)
            self.assertIn("placeholder mismatch", joined)


if __name__ == "__main__":
    unittest.main()

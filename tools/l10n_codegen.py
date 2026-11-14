#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 The TotalDrop Contributors
# SPDX-License-Identifier: MIT OR Apache-2.0

"""Single-source 35-language localization compiler and verifier (ADR 0008).

Reads the canonical ARB catalogs (`l10n/app/*.arb`, `l10n/cli/*.arb`) and
review metadata (`l10n/status.json`), enforces TotalDrop's security and
placeholder invariants across all 35 supported locales, and emits deterministic
native localization bundles for:
  - Windows 11 WinUI 3 (`winui-resw`: `Strings/<bcp47>/Resources.resw` + `locales.json`)
  - Apple SwiftUI (`apple-xcstrings`: Xcode `Localizable.xcstrings` String Catalog)
  - Browser WebAssembly UI (`web-json`: `i18n/<bcp47>.json` + `manifest.json`)
  - Ecosystem audit summary (`summary-json`)

Security invariant (ADR 0008): keys listed under `critical` in `l10n/status.json`
(or listed in a locale's `draft` array) resolve to the English template string
until a native reviewer marks the locale `reviewed: true`.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape as xml_escape

TEMPLATE_LOCALE = "en"

# Canonical 35 BCP 47 locales and their native autonyms (ADR 0008, never flags).
CANONICAL_LOCALES: tuple[tuple[str, str], ...] = (
    ("ar", "العربية"),
    ("bn", "বাংলা"),
    ("cs", "Čeština"),
    ("da", "Dansk"),
    ("de", "Deutsch"),
    ("el", "Ελληνικά"),
    ("en", "English"),
    ("es", "Español"),
    ("fa", "فارسی"),
    ("fi", "Suomi"),
    ("fr", "Français"),
    ("he", "עברית"),
    ("hi", "हिन्दी"),
    ("hu", "Magyar"),
    ("id", "Bahasa Indonesia"),
    ("it", "Italiano"),
    ("ja", "日本語"),
    ("ko", "한국어"),
    ("ms", "Bahasa Melayu"),
    ("nb", "Norsk bokmål"),
    ("nl", "Nederlands"),
    ("pl", "Polski"),
    ("pt-BR", "Português (Brasil)"),
    ("pt-PT", "Português (Portugal)"),
    ("ro", "Română"),
    ("ru", "Русский"),
    ("sv", "Svenska"),
    ("sw", "Kiswahili"),
    ("th", "ไทย"),
    ("tr", "Türkçe"),
    ("uk", "Українська"),
    ("ur", "اردو"),
    ("vi", "Tiếng Việt"),
    ("zh-Hans", "简体中文"),
    ("zh-Hant", "繁體中文"),
)

CANONICAL_TAGS: tuple[str, ...] = tuple(tag for tag, _ in CANONICAL_LOCALES)
AUTONYMS: dict[str, str] = dict(CANONICAL_LOCALES)
RTL_LOCALES: frozenset[str] = frozenset({"ar", "fa", "he", "ur"})
BASE_FALLBACK_LOCALES: tuple[str, ...] = ("pt", "zh")
ENGLISH_NO_WORDS: frozenset[str] = frozenset({"n", "no", "not"})
CRITICAL_PLACEHOLDERS: frozenset[str] = frozenset({"code", "words", "folder", "name"})

MARKUP_RE = re.compile(r"<[A-Za-z/!]")


def is_forbidden_char(ch: str) -> bool:
    """Match `totaldrop_l10n::check::forbidden` (Cc/Cf/Zl/Zp + nonchars, allowing ZWNJ/ZWJ/LRM/RLM)."""
    if ch in ("\n", "\u200C", "\u200D", "\u200E", "\u200F"):
        return False
    cp = ord(ch)
    if 0xFDD0 <= cp <= 0xFDEF or (cp & 0xFFFE) == 0xFFFE:
        return True
    return unicodedata.category(ch) in ("Cc", "Cf", "Zl", "Zp")


def _find_matching_brace(text: str, open_idx: int) -> int:
    """Return index of matching `}` for `{` at `open_idx` (plain apostrophes per gen_l10n)."""
    depth = 0
    for i in range(open_idx, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def extract_placeholders(message: str) -> set[str]:
    """Extract all ICU `{name}` and `{name, plural/select, ...}` argument names."""
    found: set[str] = set()
    n = len(message)
    i = 0
    while i < n:
        if message[i] == "{":
            close_idx = _find_matching_brace(message, i)
            if close_idx == -1:
                break
            inner = message[i + 1 : close_idx]
            parts = inner.split(",", 2)
            ident = parts[0].strip()
            if ident and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", ident):
                found.add(ident)
            if len(parts) == 3 and parts[1].strip() in (
                "plural",
                "select",
                "selectordinal",
            ):
                body = parts[2]
                bi = 0
                bn = len(body)
                while bi < bn:
                    sub_open = body.find("{", bi)
                    if sub_open == -1:
                        break
                    sub_close = _find_matching_brace(body, sub_open)
                    if sub_close == -1:
                        break
                    found |= extract_placeholders(body[sub_open + 1 : sub_close])
                    bi = sub_close + 1
            i = close_idx + 1
            continue
        i += 1
    return found


def parse_json_no_duplicates(raw_text: str, label: str) -> dict[str, Any]:
    """Parse a JSON object while rejecting duplicate keys."""

    def hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k, v in pairs:
            if k in out:
                raise ValueError(f"{label}: duplicate JSON key `{k}`")
            out[k] = v
        return out

    parsed = json.loads(raw_text, object_pairs_hook=hook)
    if not isinstance(parsed, dict):
        raise ValueError(f"{label}: top-level JSON value must be an object")
    return parsed


def arb_filename_for_locale(domain: str, tag: str) -> str:
    """Convert BCP 47 tag (`pt-BR`, `zh-Hans`) to ARB filename (`app_pt_BR.arb`)."""
    return f"{domain}_{tag.replace('-', '_')}.arb"


class CatalogBundle:
    """Validated representation of `l10n/status.json`, `l10n/app`, and `l10n/cli`."""

    def __init__(
        self,
        status: dict[str, Any],
        app_catalogs: dict[str, dict[str, str]],
        app_meta: dict[str, dict[str, Any]],
        cli_catalogs: dict[str, dict[str, str]],
    ) -> None:
        self.status = status
        self.app_catalogs = app_catalogs
        self.app_meta = app_meta
        self.cli_catalogs = cli_catalogs
        self.critical_keys: set[str] = set(status.get("critical", []))
        self.languages_meta: dict[str, dict[str, Any]] = status.get("languages", {})

    def is_reviewed(self, tag: str) -> bool:
        if tag == TEMPLATE_LOCALE:
            return True
        info = self.languages_meta.get(tag, {})
        return bool(info.get("reviewed", False))

    def draft_keys(self, tag: str) -> set[str]:
        if tag == TEMPLATE_LOCALE:
            return set()
        info = self.languages_meta.get(tag, {})
        return set(info.get("draft", []))

    def direction(self, tag: str) -> str:
        return "rtl" if tag in RTL_LOCALES else "ltr"

    def effective_app_strings(self, tag: str) -> dict[str, str]:
        """Return effective `app` strings for `tag` with critical/draft gating."""
        en_map = self.app_catalogs[TEMPLATE_LOCALE]
        if tag == TEMPLATE_LOCALE:
            return dict(sorted(en_map.items()))
        loc_map = self.app_catalogs[tag]
        base_tag = tag.split("-", 1)[0] if "-" in tag else None
        base_map = self.app_catalogs.get(base_tag, {}) if base_tag else {}
        reviewed = self.is_reviewed(tag)
        drafts = self.draft_keys(tag)

        resolved: dict[str, str] = {}
        for key in sorted(en_map):
            if key in self.critical_keys and (not reviewed or key in drafts):
                resolved[key] = en_map[key]
            elif key in loc_map:
                resolved[key] = loc_map[key]
            elif key in base_map:
                resolved[key] = base_map[key]
            else:
                resolved[key] = en_map[key]
        return resolved


def load_and_validate(l10n_dir: Path) -> tuple[CatalogBundle | None, list[str]]:
    """Load `l10n/` and validate all 35-locale security and schema invariants."""
    errors: list[str] = []
    status_path = l10n_dir / "status.json"
    if not status_path.is_file():
        return None, [f"missing status file: {status_path}"]

    try:
        status = parse_json_no_duplicates(
            status_path.read_text(encoding="utf-8"), "status.json"
        )
    except Exception as exc:  # noqa: BLE001
        return None, [f"invalid status.json: {exc}"]

    critical_list = status.get("critical")
    languages_meta = status.get("languages")
    if not isinstance(critical_list, list) or not all(
        isinstance(k, str) for k in critical_list
    ):
        errors.append("status.json: `critical` must be a non-empty list of strings")
        critical_list = []
    if not isinstance(languages_meta, dict):
        errors.append("status.json: `languages` must be a JSON object")
        languages_meta = {}

    expected_all_locales = list(CANONICAL_TAGS) + list(BASE_FALLBACK_LOCALES)
    domain_maps: dict[str, dict[str, dict[str, str]]] = {"app": {}, "cli": {}}
    app_template_meta: dict[str, dict[str, Any]] = {}

    for domain in ("app", "cli"):
        domain_dir = l10n_dir / domain
        if not domain_dir.is_dir():
            errors.append(f"missing domain directory: {domain_dir}")
            continue
        for tag in expected_all_locales:
            arb_path = domain_dir / arb_filename_for_locale(domain, tag)
            if not arb_path.is_file():
                errors.append(f"missing ARB catalog: {arb_path}")
                continue
            try:
                obj = parse_json_no_duplicates(
                    arb_path.read_text(encoding="utf-8"), f"{domain}/{arb_path.name}"
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(str(exc))
                continue

            declared_locale = str(obj.get("@@locale", "")).replace("_", "-")
            if declared_locale != tag:
                errors.append(
                    f"{domain}/{arb_path.name}: @@locale `{declared_locale}` != `{tag}`"
                )

            messages: dict[str, str] = {}
            for key, val in obj.items():
                if key.startswith("@"):
                    if (
                        domain == "app"
                        and tag == TEMPLATE_LOCALE
                        and key != "@@locale"
                        and isinstance(val, dict)
                    ):
                        app_template_meta[key[1:]] = val
                    continue
                if not isinstance(val, str):
                    errors.append(
                        f"{domain}/{tag} `{key}`: value must be string, got {type(val).__name__}"
                    )
                    continue
                messages[key] = val
            domain_maps[domain][tag] = messages

    # Verify status.json covers every non-English locale and valid noWords/cliYes
    for tag in expected_all_locales:
        if tag == TEMPLATE_LOCALE:
            continue
        if tag not in languages_meta:
            errors.append(f"status.json: missing language entry `{tag}`")
            continue
        entry = languages_meta[tag]
        if not isinstance(entry.get("reviewed"), bool):
            errors.append(f"status.json `{tag}`: `reviewed` must be a boolean")
        if not isinstance(entry.get("draft"), list):
            errors.append(f"status.json `{tag}`: `draft` must be a list")
        no_words_raw = entry.get("noWords", "")
        if not isinstance(no_words_raw, str) or not no_words_raw.strip():
            errors.append(f"status.json `{tag}`: `noWords` must be a non-empty string")
        else:
            no_tokens = {
                w.strip().casefold() for w in no_words_raw.split("|") if w.strip()
            } | ENGLISH_NO_WORDS
            cli_yes_raw = domain_maps["cli"].get(tag, {}).get("cliYes", "")
            yes_tokens = {
                w.strip().casefold() for w in cli_yes_raw.split("|") if w.strip()
            }
            overlap = sorted(no_tokens & yes_tokens)
            if overlap:
                errors.append(
                    f"cli/{tag} `cliYes`: overlaps with `noWords`: {', '.join(overlap)}"
                )

    # Validate placeholder parity, forbidden characters, and markup injection
    for domain in ("app", "cli"):
        template = domain_maps[domain].get(TEMPLATE_LOCALE)
        if not template:
            errors.append(f"{domain}: missing `{TEMPLATE_LOCALE}` template catalog")
            continue
        template_placeholders = {
            k: extract_placeholders(v) for k, v in template.items()
        }
        for tag, msg_map in sorted(domain_maps[domain].items()):
            for key, text in sorted(msg_map.items()):
                if key not in template:
                    errors.append(f"{domain}/{tag} `{key}`: unknown key not in template")
                    continue
                for ch in text:
                    if is_forbidden_char(ch):
                        errors.append(
                            f"{domain}/{tag} `{key}`: forbidden control/bidi char U+{ord(ch):04X}"
                        )
                        break
                if MARKUP_RE.search(text) and not MARKUP_RE.search(template[key]):
                    errors.append(
                        f"{domain}/{tag} `{key}`: unexpected HTML/XML markup tag"
                    )
                expected_ph = template_placeholders[key]
                actual_ph = extract_placeholders(text)
                if actual_ph != expected_ph:
                    errors.append(
                        f"{domain}/{tag} `{key}`: placeholder mismatch "
                        f"(expected {sorted(expected_ph)}, got {sorted(actual_ph)})"
                    )
                for crit_ph in CRITICAL_PLACEHOLDERS & expected_ph:
                    if f"{{{crit_ph}}}" not in text:
                        errors.append(
                            f"{domain}/{tag} `{key}`: missing literal critical placeholder `{{{crit_ph}}}`"
                        )

    # Verify every critical key exists in at least one English template
    all_en_keys = set(domain_maps["app"].get(TEMPLATE_LOCALE, {})) | set(
        domain_maps["cli"].get(TEMPLATE_LOCALE, {})
    )
    for crit_key in critical_list:
        if crit_key not in all_en_keys:
            errors.append(
                f"status.json: critical key `{crit_key}` missing from English templates"
            )

    if errors:
        return None, errors

    bundle = CatalogBundle(
        status=status,
        app_catalogs=domain_maps["app"],
        app_meta=app_template_meta,
        cli_catalogs=domain_maps["cli"],
    )
    return bundle, []


def render_winui_resw(strings: dict[str, str], descriptions: dict[str, dict[str, Any]]) -> str:
    """Render deterministic Windows App SDK / MRT Core `.resw` XML resource file."""
    spdx_copy = "SPDX-File" + "CopyrightText: 2026 The TotalDrop Contributors"
    spdx_lic = "SPDX-License-" + "Identifier: MIT OR Apache-2.0"
    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        f"<!-- {spdx_copy} -->",
        f"<!-- {spdx_lic} -->",
        "<root>",
        '  <resheader name="resmimetype">',
        "    <value>text/microsoft-resx</value>",
        "  </resheader>",
        '  <resheader name="version">',
        "    <value>2.0</value>",
        "  </resheader>",
        '  <resheader name="reader">',
        "    <value>System.Resources.ResXResourceReader, System.Windows.Forms, Version=4.0.0.0, Culture=neutral, PublicKeyToken=b77a5c561934e089</value>",
        "  </resheader>",
        '  <resheader name="writer">',
        "    <value>System.Resources.ResXResourceWriter, System.Windows.Forms, Version=4.0.0.0, Culture=neutral, PublicKeyToken=b77a5c561934e089</value>",
        "  </resheader>",
    ]
    for key in sorted(strings):
        val = xml_escape(strings[key])
        desc = descriptions.get(key, {}).get("description")
        lines.append(f'  <data name="{xml_escape(key)}" xml:space="preserve">')
        lines.append(f"    <value>{val}</value>")
        if isinstance(desc, str) and desc.strip():
            lines.append(f"    <comment>{xml_escape(desc.strip())}</comment>")
        lines.append("  </data>")
    lines.append("</root>")
    return "\n".join(lines) + "\n"


def emit_winui_resw(bundle: CatalogBundle, out_dir: Path) -> None:
    """Emit `Strings/<bcp47>/Resources.resw` for all 35 locales plus `locales.json`."""
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_locales = []
    for tag, autonym in CANONICAL_LOCALES:
        locale_dir = out_dir / tag
        locale_dir.mkdir(parents=True, exist_ok=True)
        effective = bundle.effective_app_strings(tag)
        xml_text = render_winui_resw(effective, bundle.app_meta)
        # Self-validate XML well-formedness before writing
        ET.fromstring(xml_text)
        (locale_dir / "Resources.resw").write_text(xml_text, encoding="utf-8")
        manifest_locales.append(
            {
                "tag": tag,
                "autonym": autonym,
                "dir": bundle.direction(tag),
                "reviewed": bundle.is_reviewed(tag),
                "keyCount": len(effective),
            }
        )
    manifest = {
        "defaultLocale": TEMPLATE_LOCALE,
        "localeCount": len(CANONICAL_LOCALES),
        "locales": manifest_locales,
    }
    (out_dir / "locales.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def build_apple_xcstrings(bundle: CatalogBundle) -> dict[str, Any]:
    """Build deterministic Apple String Catalog (`Localizable.xcstrings`) JSON."""
    en_strings = bundle.app_catalogs[TEMPLATE_LOCALE]
    effective_by_tag = {
        tag: bundle.effective_app_strings(tag) for tag in CANONICAL_TAGS
    }
    strings_obj: dict[str, Any] = {}
    for key in sorted(en_strings):
        entry: dict[str, Any] = {}
        desc = bundle.app_meta.get(key, {}).get("description")
        if isinstance(desc, str) and desc.strip():
            entry["comment"] = desc.strip()
        entry["extractionState"] = "manual"
        localizations: dict[str, Any] = {}
        for tag in CANONICAL_TAGS:
            reviewed = bundle.is_reviewed(tag)
            drafts = bundle.draft_keys(tag)
            is_gated_critical = key in bundle.critical_keys and (
                not reviewed or key in drafts
            )
            state = (
                "translated"
                if (reviewed or is_gated_critical)
                else "needs_review"
            )
            localizations[tag] = {
                "stringUnit": {
                    "state": state,
                    "value": effective_by_tag[tag][key],
                }
            }
        entry["localizations"] = localizations
        strings_obj[key] = entry

    return {
        "sourceLanguage": TEMPLATE_LOCALE,
        "strings": strings_obj,
        "version": "1.0",
    }


def emit_apple_xcstrings(bundle: CatalogBundle, out_target: Path) -> None:
    """Write `Localizable.xcstrings` to `out_target` (file path or parent directory)."""
    target_file = (
        out_target
        if out_target.suffix == ".xcstrings"
        else out_target / "Localizable.xcstrings"
    )
    target_file.parent.mkdir(parents=True, exist_ok=True)
    payload = build_apple_xcstrings(bundle)
    target_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def emit_web_json(bundle: CatalogBundle, out_dir: Path) -> None:
    """Write `i18n/<bcp47>.json` and `i18n/manifest.json` for the Web WASM UI."""
    out_dir.mkdir(parents=True, exist_ok=True)
    locales_index = []
    for tag, autonym in CANONICAL_LOCALES:
        effective = bundle.effective_app_strings(tag)
        doc = {
            "locale": tag,
            "autonym": autonym,
            "dir": bundle.direction(tag),
            "reviewed": bundle.is_reviewed(tag),
            "strings": effective,
        }
        (out_dir / f"{tag}.json").write_text(
            json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        locales_index.append(
            {
                "tag": tag,
                "autonym": autonym,
                "dir": bundle.direction(tag),
                "reviewed": bundle.is_reviewed(tag),
            }
        )
    manifest = {
        "defaultLocale": TEMPLATE_LOCALE,
        "localeCount": len(CANONICAL_LOCALES),
        "criticalKeys": sorted(bundle.critical_keys),
        "locales": locales_index,
    }
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def emit_summary_json(bundle: CatalogBundle, out_target: Path) -> None:
    """Write deterministic 35-language matrix summary JSON."""
    target_file = (
        out_target
        if out_target.suffix == ".json"
        else out_target / "l10n-summary.json"
    )
    target_file.parent.mkdir(parents=True, exist_ok=True)
    en_app_count = len(bundle.app_catalogs[TEMPLATE_LOCALE])
    en_cli_count = len(bundle.cli_catalogs[TEMPLATE_LOCALE])
    summary = {
        "templateLocale": TEMPLATE_LOCALE,
        "localeCount": len(CANONICAL_LOCALES),
        "rtlLocales": sorted(RTL_LOCALES),
        "reviewedLocales": [
            tag for tag in CANONICAL_TAGS if bundle.is_reviewed(tag)
        ],
        "appTemplateKeys": en_app_count,
        "cliTemplateKeys": en_cli_count,
        "criticalKeys": sorted(bundle.critical_keys),
        "locales": [
            {
                "tag": tag,
                "autonym": autonym,
                "dir": bundle.direction(tag),
                "reviewed": bundle.is_reviewed(tag),
                "appTranslatedKeys": len(bundle.app_catalogs[tag]),
                "cliTranslatedKeys": len(bundle.cli_catalogs[tag]),
            }
            for tag, autonym in CANONICAL_LOCALES
        ],
    }
    target_file.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Single-source 35-language localization compiler and verifier."
    )
    default_l10n = Path(__file__).resolve().parent.parent / "l10n"
    parser.add_argument(
        "--l10n-dir",
        type=Path,
        default=default_l10n,
        help="Path to the l10n directory containing app/, cli/, and status.json.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate all 35 locales, placeholders, bidi safety, and critical gating.",
    )
    parser.add_argument(
        "--emit",
        choices=("winui-resw", "apple-xcstrings", "web-json", "summary-json"),
        help="Target native bundle format to emit.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Output directory or file path for --emit.",
    )
    args = parser.parse_args(argv)

    if not args.check and not args.emit:
        parser.error("specify --check and/or --emit <format> --out <path>")
    if args.emit and not args.out:
        parser.error("--out <path> is required when --emit is set")

    bundle, errors = load_and_validate(args.l10n_dir)
    if errors or bundle is None:
        for err in errors:
            print(f"error: {err}", file=sys.stderr)
        return 1

    if args.check:
        reviewed = [t for t in CANONICAL_TAGS if bundle.is_reviewed(t)]
        print(
            f"l10n-codegen check OK: {len(CANONICAL_TAGS)} canonical locales "
            f"({len(RTL_LOCALES)} RTL, reviewed={reviewed}), "
            f"{len(bundle.app_catalogs[TEMPLATE_LOCALE])} app keys, "
            f"{len(bundle.cli_catalogs[TEMPLATE_LOCALE])} cli keys, "
            f"{len(bundle.critical_keys)} critical security keys."
        )

    if args.emit == "winui-resw":
        emit_winui_resw(bundle, args.out)
        print(f"emitted 35 WinUI 3 .resw bundles to {args.out}")
    elif args.emit == "apple-xcstrings":
        emit_apple_xcstrings(bundle, args.out)
        print(f"emitted Apple String Catalog to {args.out}")
    elif args.emit == "web-json":
        emit_web_json(bundle, args.out)
        print(f"emitted 35 Web JSON catalogs to {args.out}")
    elif args.emit == "summary-json":
        emit_summary_json(bundle, args.out)
        print(f"emitted 35-locale summary JSON to {args.out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

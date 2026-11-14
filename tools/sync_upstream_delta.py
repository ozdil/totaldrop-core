#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 The TotalDrop Contributors
# SPDX-License-Identifier: MIT OR Apache-2.0
"""Upstream delta auditor and modular repository synchronizer for TotalDrop.

Maps commits and file changes from the upstream monorepo (`totaldrop-app/totaldrop`)
into the 11 standalone Multi-Platform x Multi-Architecture repositories under the
`totaldrop-app` GitHub organization, without ever mutating the upstream repository.

Supports both pre-cloned directories (`00-core` .. `10-web-wasm` or GitHub names
`totaldrop-core` .. `totaldrop-web-wasm`) and zero-local-footprint ephemeral cloud
clones (`--clone-from-github`).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

DEFAULT_BASELINE = "c86c298f678eb062c670efb2d34ce79dfda08ec1"
DEFAULT_GITHUB_ORG = "totaldrop-app"

MODULE_TO_GITHUB_REPO: dict[str, str] = {
    "00-core": "totaldrop-core",
    "01-formal-fuzz": "totaldrop-formal-fuzz",
    "02-servers": "totaldrop-servers",
    "03-site": "totaldrop-site",
    "04-linux": "totaldrop-linux",
    "05-android": "totaldrop-android",
    "06-windows": "totaldrop-windows",
    "07-macos": "totaldrop-macos",
    "08-ios-and-tvos": "totaldrop-ios-tvos",
    "09-cli-and-bsd": "totaldrop-cli-bsd",
    "10-web-wasm": "totaldrop-web-wasm",
}


@dataclass(frozen=True)
class PathRule:
    """Maps an upstream prefix or exact file to a modular repository path."""

    upstream_prefix: str
    module: str
    dest_prefix: str
    exact: bool = False


MAPPING_RULES: tuple[PathRule, ...] = (
    *(
        PathRule(f"crates/{crate}/", mod, f"crates/{crate}/")
        for crate in ("totaldrop-crypto", "totaldrop-proto", "totaldrop-l10n")
        for mod in (
            "00-core",
            "01-formal-fuzz",
            "04-linux",
            "05-android",
            "06-windows",
            "07-macos",
            "08-ios-and-tvos",
            "09-cli-and-bsd",
            "10-web-wasm",
        )
    ),
    PathRule("crates/totaldrop-proto/", "02-servers", "crates/totaldrop-proto/"),
    *(
        PathRule("crates/totaldrop-core/", mod, "crates/totaldrop-core/")
        for mod in (
            "00-core",
            "01-formal-fuzz",
            "04-linux",
            "05-android",
            "06-windows",
            "07-macos",
            "08-ios-and-tvos",
            "09-cli-and-bsd",
        )
    ),
    *(
        PathRule("l10n/", mod, "l10n/")
        for mod in (
            "00-core",
            "01-formal-fuzz",
            "04-linux",
            "05-android",
            "06-windows",
            "07-macos",
            "08-ios-and-tvos",
            "09-cli-and-bsd",
            "10-web-wasm",
        )
    ),
    PathRule("l10n/status.json", "03-site", "vendor/l10n/status.json", exact=True),
    PathRule("l10n/tests/", "03-site", "vendor/l10n/tests/"),
    PathRule("crates/totaldrop-cli/", "04-linux", "crates/totaldrop-cli/"),
    PathRule("crates/totaldrop-cli/", "09-cli-and-bsd", "crates/totaldrop-cli/"),
    PathRule("formal/", "01-formal-fuzz", "formal/"),
    PathRule("fuzz/fuzz_targets/", "01-formal-fuzz", "fuzz/fuzz_targets/"),
    PathRule("server/rendezvous-worker/src/", "02-servers", "cloudflare-rendezvous/src/"),
    PathRule("server/rendezvous-worker/test/", "02-servers", "cloudflare-rendezvous/test/"),
    PathRule("server/rendezvous-worker/package.json", "02-servers", "cloudflare-rendezvous/package.json", exact=True),
    PathRule("server/rendezvous-worker/package-lock.json", "02-servers", "cloudflare-rendezvous/package-lock.json", exact=True),
    PathRule("server/rendezvous-worker/wrangler.jsonc", "02-servers", "cloudflare-rendezvous/wrangler.jsonc", exact=True),
    PathRule("server/relay-worker/src/", "02-servers", "cloudflare-relay/src/"),
    PathRule("server/relay-worker/test/", "02-servers", "cloudflare-relay/test/"),
    PathRule("server/relay-worker/package.json", "02-servers", "cloudflare-relay/package.json", exact=True),
    PathRule("server/relay-worker/package-lock.json", "02-servers", "cloudflare-relay/package-lock.json", exact=True),
    PathRule("server/relay-worker/wrangler.jsonc", "02-servers", "cloudflare-relay/wrangler.jsonc", exact=True),
    PathRule("server/totaldrop-rendezvous/src/", "02-servers", "rust-shared/totaldrop-rendezvous/src/"),
    PathRule("server/totaldrop-relay/src/", "02-servers", "rust-shared/totaldrop-relay/src/"),
    PathRule("server/tools/", "02-servers", "rust-shared/tools/"),
    PathRule("site/public/", "03-site", "public/"),
    PathRule("site/functions/", "03-site", "functions/"),
    PathRule("site/privacy/", "03-site", "privacy/"),
    PathRule("site/team/", "03-site", "team/"),
    PathRule("site/wrangler.toml", "03-site", "wrangler.toml", exact=True),
    PathRule("SECURITY.md", "03-site", "SECURITY.md", exact=True),
    PathRule("app/assets/logo.svg", "03-site", "vendor/logo.svg", exact=True),
    PathRule("packaging/linux/app.totaldrop.TotalDrop.svg", "03-site", "vendor/app.totaldrop.TotalDrop.svg", exact=True),
    PathRule("app/android/app/build.gradle.kts", "03-site", "vendor/android/build.gradle.kts", exact=True),
    PathRule("app/android/app/src/main/AndroidManifest.xml", "03-site", "vendor/android/AndroidManifest.xml", exact=True),
    PathRule("linux/qml/", "04-linux", "ui-qt6-wayland/qml/"),
    PathRule("linux/src/", "04-linux", "ui-qt6-wayland/src/"),
    PathRule("packaging/linux/", "04-linux", "packaging-common/linux/"),
    PathRule("app/lib/", "05-android", "ui-m3-expressive/lib/"),
    PathRule("app/test/", "05-android", "ui-m3-expressive/test/"),
    PathRule("app/android/", "05-android", "ui-m3-expressive/android/"),
    PathRule("app/assets/", "05-android", "ui-m3-expressive/assets/"),
    PathRule("app/rust/src/", "05-android", "ui-m3-expressive/rust/src/"),
    PathRule("app/pubspec.yaml", "05-android", "ui-m3-expressive/pubspec.yaml", exact=True),
)

# Files inside mapped prefixes that intentionally carry standalone module adaptations
# (ADR 0019 English doc comments, standalone directory paths, or rustfmt wrapping).
STANDALONE_PROTECTED_RELPATHS: frozenset[tuple[str, str]] = frozenset(
    {
        ("01-formal-fuzz", "fuzz/fuzz_targets/message.rs"),
        ("04-linux", "crates/totaldrop-cli/Cargo.toml"),
        ("04-linux", "crates/totaldrop-cli/tests/end_to_end.rs"),
        ("04-linux", "crates/totaldrop-cli/tests/program.rs"),
        ("04-linux", "crates/totaldrop-core/src/error.rs"),
        ("04-linux", "crates/totaldrop-l10n/src/lib.rs"),
        ("04-linux", "packaging-common/linux/file-managers/test_totaldrop_nautilus.py"),
        ("04-linux", "packaging-common/linux/file-managers/totaldrop_nautilus.py"),
        ("04-linux", "packaging-common/linux/install.sh"),
        ("04-linux", "ui-qt6-wayland/qml/Mark.qml"),
        ("04-linux", "ui-qt6-wayland/src/desktop.rs"),
        ("04-linux", "ui-qt6-wayland/src/main.rs"),
        ("04-linux", "ui-qt6-wayland/src/theme/host.rs"),
        ("04-linux", "ui-qt6-wayland/src/theme/mod.rs"),
    }
)


def resolve_module_dir(modules_root: Path, module_key: str) -> Path:
    """Resolve either `<modules_root>/00-core` or `<modules_root>/totaldrop-core`."""
    direct = modules_root / module_key
    if direct.exists():
        return direct
    repo_name = MODULE_TO_GITHUB_REPO.get(module_key, module_key)
    by_repo = modules_root / repo_name
    if by_repo.exists():
        return by_repo
    return direct


def map_upstream_path(rel_path: str) -> list[tuple[str, str]]:
    """Return list of `(module_key, module_rel_path)` targets for an upstream path."""
    targets: list[tuple[str, str]] = []
    for rule in MAPPING_RULES:
        if rule.exact:
            if rel_path == rule.upstream_prefix:
                targets.append((rule.module, rule.dest_prefix))
        elif rel_path.startswith(rule.upstream_prefix):
            suffix = rel_path[len(rule.upstream_prefix) :]
            dest = f"{rule.dest_prefix}{suffix}"
            if (rule.module, dest) not in STANDALONE_PROTECTED_RELPATHS:
                targets.append((rule.module, dest))
    return targets


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def git_changed_files(upstream: Path, base: str, head: str) -> list[tuple[str, str]]:
    """Return list of `(status, path)` between `base` and `head` in `upstream`."""
    out = subprocess.check_output(
        [
            "git",
            "-C",
            str(upstream),
            "-c",
            "core.quotePath=false",
            "diff",
            "--name-status",
            "--no-renames",
            f"{base}..{head}",
        ],
        text=True,
    )
    entries: list[tuple[str, str]] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        status, path = line.split("\t", 1)
        entries.append((status.strip(), path.strip()))
    return entries


def clone_cloud_workspace(temp_root: Path, org: str) -> tuple[Path, Path]:
    """Ephemerally clone upstream and all 11 modular repos into `temp_root`."""
    upstream_dir = temp_root / "upstream"
    modules_dir = temp_root / "modules"
    modules_dir.mkdir(parents=True, exist_ok=True)
    subprocess.check_call(
        ["git", "clone", "--quiet", f"https://github.com/{org}/totaldrop.git", str(upstream_dir)]
    )
    for mod_key, repo_name in MODULE_TO_GITHUB_REPO.items():
        subprocess.check_call(
            [
                "git",
                "clone",
                "--quiet",
                "--depth=1",
                f"https://github.com/{org}/{repo_name}.git",
                str(modules_dir / mod_key),
            ]
        )
    return upstream_dir, modules_dir


def cmd_delta(upstream: Path, base: str, head: str, as_json: bool) -> int:
    head_sha = subprocess.check_output(
        ["git", "-C", str(upstream), "rev-parse", head], text=True
    ).strip()
    changes = git_changed_files(upstream, base, head)
    by_module: dict[str, list[dict[str, str]]] = {}
    unmapped: list[str] = []

    for status, rel_path in changes:
        targets = map_upstream_path(rel_path)
        if not targets:
            unmapped.append(f"{status}\t{rel_path}")
            continue
        for mod, dest in targets:
            repo_name = MODULE_TO_GITHUB_REPO.get(mod, mod)
            by_module.setdefault(repo_name, []).append(
                {"status": status, "upstream": rel_path, "dest": dest}
            )

    if as_json:
        print(
            json.dumps(
                {
                    "base": base,
                    "head": head_sha,
                    "changed_upstream_files": len(changes),
                    "affected_repositories": by_module,
                    "unmapped_or_protected": unmapped,
                },
                indent=2,
            )
        )
        return 0

    print(f"Upstream delta: {base[:7]}..{head_sha[:7]} ({len(changes)} upstream files changed)")
    if not changes:
        print("All 11 modular repositories are already at the latest upstream commit.")
        return 0
    for repo_name in sorted(by_module):
        items = by_module[repo_name]
        print(f"\n[{repo_name}] ({len(items)} mapped file updates):")
        for item in items:
            print(f"  {item['status']} {item['upstream']} -> {item['dest']}")
    if unmapped:
        print(f"\n[monorepo-only / protected] ({len(unmapped)} files):")
        for entry in unmapped:
            print(f"  {entry}")
    return 0


def cmd_verify(upstream: Path, modules_dir: Path) -> int:
    tracked = subprocess.check_output(
        ["git", "-C", str(upstream), "-c", "core.quotePath=false", "ls-files"],
        text=True,
    ).splitlines()

    checked = 0
    drifted: list[str] = []
    for rel_path in tracked:
        src_file = upstream / rel_path
        if not src_file.is_file():
            continue
        targets = map_upstream_path(rel_path)
        if not targets:
            continue
        src_hash = sha256_file(src_file)
        for mod, dest in targets:
            mod_root = resolve_module_dir(modules_dir, mod)
            dst_file = mod_root / dest
            checked += 1
            label = MODULE_TO_GITHUB_REPO.get(mod, mod)
            if not dst_file.is_file():
                drifted.append(f"MISSING: {label}/{dest} (from {rel_path})")
            elif sha256_file(dst_file) != src_hash:
                drifted.append(f"DIFFERS: {label}/{dest} (from {rel_path})")

    if drifted:
        print(f"Parity check found {len(drifted)} difference(s) across {checked} mapped file pairs:")
        for d in drifted[:50]:
            print(f"  - {d}")
        return 1

    print(f"Parity OK: {checked} mapped file pairs across 11 repositories match upstream byte-for-byte.")
    return 0


def cmd_sync(upstream: Path, modules_dir: Path, base: str, head: str, apply_changes: bool) -> int:
    changes = git_changed_files(upstream, base, head)
    ops: list[tuple[str, str, Path, Path, Path]] = []
    for status, rel_path in changes:
        for mod, dest in map_upstream_path(rel_path):
            mod_root = resolve_module_dir(modules_dir, mod)
            ops.append((status, mod, mod_root, upstream / rel_path, mod_root / dest))

    if not ops:
        print("Nothing to synchronize.")
        return 0

    mode_label = "APPLY" if apply_changes else "DRY-RUN"
    print(f"[{mode_label}] {len(ops)} file operation(s) across modular repositories:")
    for status, mod, mod_root, src, dst in ops:
        label = MODULE_TO_GITHUB_REPO.get(mod, mod)
        print(f"  {status} {label}: {dst.relative_to(mod_root)}")
        if apply_changes:
            if status == "D":
                if dst.exists():
                    dst.unlink()
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--upstream", type=Path, default=Path("/home/antigravity/totaldrop-app/totaldrop"))
    p.add_argument("--modules", type=Path, default=Path("/home/antigravity/totaldrop-modules"))
    p.add_argument(
        "--clone-from-github",
        action="store_true",
        help="Clone upstream and modular repos into an auto-cleaned temporary directory",
    )
    p.add_argument("--github-org", default=DEFAULT_GITHUB_ORG, help="GitHub organization login")
    sub = p.add_subparsers(dest="command", required=True)

    d = sub.add_parser("delta", help="Audit upstream commits and list affected modular repos")
    d.add_argument("--base", default=DEFAULT_BASELINE)
    d.add_argument("--head", default="HEAD")
    d.add_argument("--json", action="store_true")

    sub.add_parser("verify", help="Verify SHA-256 parity of all mapped shared files against upstream")

    s = sub.add_parser("sync", help="Synchronize upstream delta into modular repositories")
    s.add_argument("--base", default=DEFAULT_BASELINE)
    s.add_argument("--head", default="HEAD")
    s.add_argument("--apply", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.clone_from_github:
        with tempfile.TemporaryDirectory(prefix="totaldrop-cloud-sync-") as tmp:
            upstream_dir, modules_dir = clone_cloud_workspace(Path(tmp), args.github_org)
            if args.command == "delta":
                return cmd_delta(upstream_dir, args.base, args.head, args.json)
            if args.command == "verify":
                return cmd_verify(upstream_dir, modules_dir)
            if args.command == "sync":
                return cmd_sync(upstream_dir, modules_dir, args.base, args.head, args.apply)
            return 1

    if args.command == "delta":
        return cmd_delta(args.upstream, args.base, args.head, args.json)
    if args.command == "verify":
        return cmd_verify(args.upstream, args.modules)
    if args.command == "sync":
        return cmd_sync(args.upstream, args.modules, args.base, args.head, args.apply)
    return 1


if __name__ == "__main__":
    sys.exit(main())

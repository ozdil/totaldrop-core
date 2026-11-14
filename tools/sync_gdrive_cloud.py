#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 The TotalDrop Contributors
# SPDX-License-Identifier: MIT OR Apache-2.0
"""Cloud-only GitHub -> Google Drive backup & release-archive synchronizer.

Packages full Git bundles (`git bundle create <repo>.bundle --all`) and clean,
reproducible `.tar.zst` source archives (`git archive HEAD`) for the entire
`totaldrop-app` GitHub organization inside an auto-cleaned ephemeral temporary
directory, then uploads or updates them in place under Google Drive's
`projects/totaldrop-ecosystem/` workspace (`gdrive mutate upload` / `update`).

Zero persistent local files are left behind after execution.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_GITHUB_ORG = "totaldrop-app"
DEFAULT_ECOSYSTEM_FOLDER_ID = "17U5qTizl3qwj9X1nBGF-JZOOl0rmrCJW"
DEFAULT_BUNDLES_FOLDER_ID = "1IwwwJYCE31NMagu2nHzf-jlbJJWC1gQe"
DEFAULT_ARCHIVES_FOLDER_ID = "1E2OEjQ_iyXLA2lJVsYOdHAlxnqUWeSxL"
DEFAULT_TOOLS_FOLDER_ID = "1H2zBwb6A13unnr1XVtMiqKXOzAcBQ5ie"

ALL_REPOSITORIES: tuple[str, ...] = (
    "totaldrop",
    ".github",
    "totaldrop-core",
    "totaldrop-formal-fuzz",
    "totaldrop-servers",
    "totaldrop-site",
    "totaldrop-linux",
    "totaldrop-android",
    "totaldrop-windows",
    "totaldrop-macos",
    "totaldrop-ios-tvos",
    "totaldrop-cli-bsd",
    "totaldrop-web-wasm",
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def list_drive_folder_files(folder_id: str) -> dict[str, str]:
    """Return `{filename: file_id}` for non-trashed items in `folder_id`."""
    raw = subprocess.check_output(
        ["gdrive", "readonly", "ls", folder_id, "--max", "200", "--json"],
        text=True,
    )
    data = json.loads(raw)
    items = data.get("files", data) if isinstance(data, dict) else data
    mapping: dict[str, str] = {}
    for item in items:
        if isinstance(item, dict) and "name" in item and "id" in item:
            mapping[str(item["name"])] = str(item["id"])
    return mapping


def upsert_drive_file(local_path: Path, parent_folder_id: str, existing: dict[str, str]) -> None:
    """Update file in place if present in `existing`, otherwise upload into `parent_folder_id`."""
    name = local_path.name
    if name in existing:
        subprocess.check_call(["gdrive", "mutate", "update", existing[name], str(local_path)])
    else:
        subprocess.check_call(
            ["gdrive", "mutate", "upload", str(local_path), "--parent", parent_folder_id]
        )


def archive_stem(repo: str) -> str:
    return "org-dot-github" if repo == ".github" else repo


def sync_all_to_gdrive(
    org: str,
    bundles_folder_id: str,
    archives_folder_id: str,
    tools_folder_id: str,
) -> dict[str, object]:
    existing_bundles = list_drive_folder_files(bundles_folder_id)
    existing_archives = list_drive_folder_files(archives_folder_id)
    existing_tools = list_drive_folder_files(tools_folder_id)

    manifest_repos: list[dict[str, object]] = []
    checksum_lines: list[str] = []

    with tempfile.TemporaryDirectory(prefix="totaldrop-gdrive-sync-") as tmp:
        tmp_root = Path(tmp)
        for repo in ALL_REPOSITORIES:
            stem = archive_stem(repo)
            clone_dir = tmp_root / f"clone-{stem}"
            url = f"https://github.com/{org}/{repo}.git"
            print(f"[cloud-sync] Cloning {org}/{repo} ...", flush=True)
            subprocess.check_call(["git", "clone", "--quiet", "--mirror", url, str(clone_dir)])

            head_sha = subprocess.check_output(
                ["git", "-C", str(clone_dir), "rev-parse", "HEAD"], text=True
            ).strip()

            bundle_path = tmp_root / f"{stem}.bundle"
            subprocess.check_call(
                ["git", "-C", str(clone_dir), "bundle", "create", str(bundle_path), "--all"]
            )
            bundle_sha256 = sha256_file(bundle_path)
            checksum_lines.append(f"{bundle_sha256}  git-bundles/{bundle_path.name}")
            upsert_drive_file(bundle_path, bundles_folder_id, existing_bundles)

            tar_zst_path = tmp_root / f"{stem}-{head_sha[:7]}.tar.zst"
            # Also publish stable filename `<stem>.tar.zst` so updates preserve Drive file IDs
            stable_tar_zst = tmp_root / f"{stem}.tar.zst"
            with stable_tar_zst.open("wb") as out_f:
                p_arc = subprocess.Popen(
                    ["git", "-C", str(clone_dir), "archive", "--format=tar", f"--prefix={stem}/", "HEAD"],
                    stdout=subprocess.PIPE,
                )
                subprocess.check_call(["zstd", "-q", "-19", "-f"], stdin=p_arc.stdout, stdout=out_f)
                if p_arc.stdout is not None:
                    p_arc.stdout.close()
                if p_arc.wait() != 0:
                    raise RuntimeError(f"git archive failed for {repo}")

            archive_sha256 = sha256_file(stable_tar_zst)
            checksum_lines.append(f"{archive_sha256}  source-archives/{stable_tar_zst.name}")
            upsert_drive_file(stable_tar_zst, archives_folder_id, existing_archives)
            _ = tar_zst_path

            manifest_repos.append(
                {
                    "repository": f"{org}/{repo}",
                    "github_url": f"https://github.com/{org}/{repo}",
                    "head_sha": head_sha,
                    "bundle_file": f"git-bundles/{bundle_path.name}",
                    "bundle_sha256": bundle_sha256,
                    "bundle_bytes": bundle_path.stat().st_size,
                    "archive_file": f"source-archives/{stable_tar_zst.name}",
                    "archive_sha256": archive_sha256,
                    "archive_bytes": stable_tar_zst.stat().st_size,
                }
            )

        sums_path = tmp_root / "SHA256SUMS.txt"
        sums_path.write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
        upsert_drive_file(sums_path, archives_folder_id, existing_archives)

        manifest = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "github_organization": org,
            "cloud_workflow": "GitHub (source & CI) + Google Drive (bundles, archives & Docs) + Cloudflare (Workers & Pages)",
            "repository_count": len(manifest_repos),
            "repositories": manifest_repos,
        }
        manifest_path = tmp_root / "CLOUD_ECOSYSTEM_MANIFEST.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        upsert_drive_file(manifest_path, tools_folder_id, existing_tools)

        # Mirror tool scripts themselves into Google Drive `tools/`
        tools_src_dir = Path(__file__).resolve().parent
        for script_name in (
            "sync_upstream_delta.py",
            "test_sync_upstream_delta.py",
            "sync_gdrive_cloud.py",
        ):
            candidate = tools_src_dir / script_name
            if candidate.is_file():
                upsert_drive_file(candidate, tools_folder_id, existing_tools)

    return manifest


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--github-org", default=DEFAULT_GITHUB_ORG)
    p.add_argument("--bundles-folder-id", default=DEFAULT_BUNDLES_FOLDER_ID)
    p.add_argument("--archives-folder-id", default=DEFAULT_ARCHIVES_FOLDER_ID)
    p.add_argument("--tools-folder-id", default=DEFAULT_TOOLS_FOLDER_ID)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = sync_all_to_gdrive(
        org=args.github_org,
        bundles_folder_id=args.bundles_folder_id,
        archives_folder_id=args.archives_folder_id,
        tools_folder_id=args.tools_folder_id,
    )
    print(f"Synced {manifest['repository_count']} repositories to Google Drive successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

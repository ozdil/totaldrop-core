# Multi-Repository Cloud Development Guide

TotalDrop operates across **11 modular GitHub repositories** under
`https://github.com/totaldrop-app` ([0020](decisions/0020-modular-subplatform-matrix.md))
with a **100% Cloud-Native (`GitHub + Google Drive + Cloudflare`)** workflow.

## 1. Repository Map & Build Commands

- **`totaldrop-core`**:
  - `cargo test --workspace --locked`
  - `cargo clippy --workspace --all-targets --locked -- -D warnings`
  - `./targets/build-arch.sh wasm32-simd128 --locked`
- **`totaldrop-formal-fuzz`**:
  - `tamarin-prover --prove formal/*.spthy`
  - `cargo test --workspace --locked`
- **`totaldrop-servers`**:
  - `npm --prefix cloudflare-rendezvous test && npm --prefix cloudflare-relay test`
  - `cargo test --workspace --locked`
- **`totaldrop-site`**:
  - `node tools/check-i18n.mjs && node tools/privacy.mjs --check && node --test tools/test-*.mjs`
- **Client Platform Repositories (`totaldrop-linux`, `totaldrop-android`, `totaldrop-windows`, `totaldrop-macos`, `totaldrop-ios-tvos`, `totaldrop-cli-bsd`, `totaldrop-web-wasm`)**:
  - Each repository contains shared vendored/synced core crates (`crates/`),
    35-language resources (`l10n/`), native UI bridge code, and isolated
    per-architecture build recipes (`subplatforms/<format>/<arch>/` and
    `target-*/`).

## 2. Pinned Toolchain Versions

All repositories share a single pinned toolchain baseline:
- **Rust:** `1.99.1` (`rust-toolchain.toml`)
- **Node.js:** `24` LTS (for Workers, site verification, and WASM harnesses)
- **Flutter (Android):** `3.47.8` (Temurin JDK `21`)
- **REUSE Compliance:** `fsfe/reuse:6.2.0` (`./tools/check-spdx.sh`)

## 3. Cloud Backup & Zero-Local-Footprint Synchronization

Run `python3 tools/sync_gdrive_cloud.py` from `totaldrop-core` inside an
ephemeral workspace to mirror verified `.bundle` Git repositories, deterministic
`.tar.gz` source archives, `SHA256SUMS.txt`, and `CLOUD_ECOSYSTEM_MANIFEST.json`
directly into Google Drive (`projects/totaldrop-ecosystem/`).

# 0020: Modular 11-repository architecture and 55-unit sub-platform × CPU matrix

- **Status:** Accepted, 14 November 2026 (Supersedes [0001](0001-one-repository.md))
- **Context:** As TotalDrop expands across every desktop, mobile, TV, BSD, CLI,
  and Web platform with an international engineering team, a single monorepo
  couples unrelated toolchains, slows CI feedback, and blurs ownership across
  package formats (`deb`, `rpm`, `tar.gz`, `arch`, `flatpak`, `appimage`,
  `msix`, `winget`, `dmg`, `pkg`, `play-aab`, `fdroid-apk`, `ipa`, `bsd-pkg`,
  `wasm32`) and CPU architectures (`x86_64`, `arm64`, `riscv64`, `wasm32`).
- **Decision:**
  1. **11 Standalone Public Repositories under `totaldrop-app`:**
     - `totaldrop-core`: Shared Rust protocol (`totaldrop-proto`), hybrid PQC
       cryptography (`totaldrop-crypto`), transfer engine (`totaldrop-core`),
       Ghost Ring primitives, single-source 35-language `l10n/` + `l10n-codegen`,
       and canonical English documentation (`docs/`).
     - `totaldrop-formal-fuzz`: Tamarin symbolic security proofs (`formal/`)
       and continuous `cargo-fuzz` harnesses (`fuzz/`).
     - `totaldrop-servers`: Cloudflare Rendezvous & Relay Workers plus
       self-hostable Rust servers (`x86_64` and `arm64`).
     - `totaldrop-site`: `totaldrop.app` Cloudflare Pages static site with 35
       per-language URLs and embedded Web client integration.
     - `totaldrop-linux`: Native Qt 6 / Wayland desktop client (`16` isolated
       units: `deb`, `rpm`, `tar-gz`, `arch` × `x86_64`, `arm64`, `riscv64` +
       `flatpak`, `appimage` × `x86_64`, `arm64`).
     - `totaldrop-android`: Android & Android TV client (`10` isolated units:
       `play-aab` + `fdroid-apk`, `split-apk`, `tv-apk` × `arm64-v8a`,
       `armeabi-v7a`, `x86_64`).
     - `totaldrop-windows`: Native WinUI 3 client (`6` isolated units: `msix`,
       `winget`, `portable-zip` × `x86_64`, `arm64`).
     - `totaldrop-macos`: Native SwiftUI 6 / AppKit client (`6` isolated units:
       `dmg`, `pkg`, `homebrew` × `arm64`, `x86_64`).
     - `totaldrop-ios-tvos`: Native SwiftUI 6 iOS, iPadOS & tvOS client (`6`
       isolated units: `ios-ipa`, `tvos-ipa` × `arm64`, `sim-arm64`,
       `sim-x86_64`).
     - `totaldrop-cli-bsd`: Standalone CLI & BSD packages (`9` isolated units:
       `static-tar-gz`, `freebsd-pkg`, `openbsd-pkg` × `x86_64`, `arm64`,
       `riscv64`).
     - `totaldrop-web-wasm`: Zero-framework Rust/WASM browser client (`2`
       isolated units: `wasm32-simd128`, `wasm32-baseline`).
  2. **Sub-Platform × CPU Isolation Contract:** Inside each platform repository,
     every `subplatforms/<format>/<arch>/` unit owns its deterministic build
     recipe (`SOURCE_DATE_EPOCH`), dedicated GitHub Actions workflow, independent
     version tag, `SHA256SUMS`, and Sigstore build provenance (`*.sigstore.json`).
  3. **Two-Stage Anonymous Membership ([0013](0013-ghost-ring-accounts.md)):**
     Zero-account transfers remain the default forever; opt-in Ghost Ring ships
     in Stage 1 ("My Devices", up to 16 devices, codeless 1-tap transfer) and
     Stage 2 ("Known Contacts", Witnessed Transparency Log, ARC, and 24-word
     time-locked recovery).
  4. **100% English & 100% Cloud-Native Operations ([0019](0019-english-by-default.md)):**
     All GitHub issues, pull requests, discussions, milestones, templates, and
     documents are conducted in English; verified Git bundles and SHA-256
     source archives mirror automatically to Google Drive with zero local
     machine state.

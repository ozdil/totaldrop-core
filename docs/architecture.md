# Architecture Overview

TotalDrop sends files of any size directly from any platform to any platform,
end-to-end encrypted, in 35 languages, without requiring an account (with
opt-in serverless post-quantum **Ghost Ring** device management on the roadmap;
see [accounts.md](accounts.md)).

Related specifications:
- Wire & cryptographic protocol notes: [protocol-v0.1-notes.md](protocol-v0.1-notes.md)
- Threat model & security boundaries: [threat-model.md](threat-model.md)
- Decision records (`0001–0020`): [decisions/README.md](decisions/README.md)
- Engineering & release workflow: [process.md](process.md) and [development.md](development.md)

## 1. Modular 11-Repository Ecosystem

| Repository | Responsibility | License |
| --- | --- | --- |
| `totaldrop-core` | Shared Rust crates (`totaldrop-crypto`, `totaldrop-proto`, `totaldrop-core`, `totaldrop-l10n`), 35-language `l10n/` single source of truth, `l10n-codegen`, and canonical `docs/` | `MIT OR Apache-2.0` |
| `totaldrop-formal-fuzz` | Tamarin Prover symbolic cryptographic models (`formal/`) and `cargo-fuzz` targets (`fuzz/`) | `MIT OR Apache-2.0` |
| `totaldrop-servers` | Cloudflare Workers (`cloudflare-rendezvous`, `cloudflare-relay`) + self-hostable Rust servers | `AGPL-3.0-or-later` (`proto`: `MIT OR Apache-2.0`) |
| `totaldrop-site` | `totaldrop.app` static site (35 locale URLs, privacy policy, `/r` deep links, Cloudflare Pages) | `GPL-3.0-or-later` |
| `totaldrop-linux` | Qt 6 / QML Wayland native desktop app + 16 sub-platform × CPU package units (`deb`, `rpm`, `tar.gz`, `arch`, `flatpak`, `appimage`) | `GPL-3.0-or-later` |
| `totaldrop-android` | Flutter Material 3 Expressive + Android TV app + 10 sub-platform × ABI units (`play-aab`, `fdroid-apk`, `split-apk`, `tv-apk`) | `GPL-3.0-or-later` |
| `totaldrop-windows` | WinUI 3 native desktop app + Rust IPC/FFI bridge + 6 units (`msix`, `winget`, `portable-zip` × `x86_64`, `arm64`) | `GPL-3.0-or-later` |
| `totaldrop-macos` | SwiftUI 6 / AppKit app + `IOPMAssertion` guard + 6 units (`dmg`, `pkg`, `homebrew` × `arm64`, `x86_64`) | `GPL-3.0-or-later` |
| `totaldrop-ios-tvos` | SwiftUI 6 iOS, iPadOS & tvOS app + Share Extension + `BGContinuedProcessingTask` + 6 units | `GPL-3.0-or-later` |
| `totaldrop-cli-bsd` | Terminal CLI (`totaldrop`) + 9 units (`static-tar-gz`, `freebsd-pkg`, `openbsd-pkg` × `x86_64`, `arm64`, `riscv64`) | `MIT OR Apache-2.0` |
| `totaldrop-web-wasm` | Zero-framework Rust/WASM browser peer (`wasm32-simd128` + `wasm32-baseline`) | `GPL-3.0-or-later` |

## 2. End-to-End Transfer Lifecycle

1. **Rendezvous & PAKE (`CPace` over Ristretto255):** Sender and receiver meet in
   a short-lived Cloudflare Durable Object mailbox (`rendezvous.totaldrop.app`)
   addressed by an ephemeral numeric slot, executing balanced `CPace` over the
   one-time transfer code (or via a Ghost Ring daily blinded mailbox in Stage 1).
2. **Authenticated Path Hints (`HINTS`):** Peers exchange encrypted LAN
   addresses, Cloudflare STUN (`stun.cloudflare.com`) reflexive endpoints,
   temporary UPnP/NAT-PMP/PCP router mappings, and one-time Ed25519 QUIC keys.
3. **Hybrid Post-Quantum Session (`Noise XXpsk3` + `ML-KEM-768`):** Peers race
   direct UDP/QUIC (`IPv4 + IPv6 Happy Eyeballs`) against the Cloudflare Durable
   Object WebSocket Relay (`relay.totaldrop.app`); Web peers stream the exact
   same E2EE protocol over `RelayStreamTransport` / `WebTransport`.
4. **Chunked Authenticated Streaming (`STREAM` + `BLAKE3`):** File manifests and
   chunks are authenticated end-to-end, written strictly inside the target
   receive directory without path traversal or silent overwrites, and verified
   against `BLAKE3` digests.

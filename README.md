# TotalDrop Core (`00-core`)

Standalone protocol, cryptography, transport engine, and localization workspace extracted from [`totaldrop-app/totaldrop`](https://github.com/totaldrop-app/totaldrop) at upstream commit `ebe2b19` (`v0.2.0-beta.5`).

All workspace crates are dual-licensed under `MIT OR Apache-2.0` and enforce `unsafe_code = "forbid"` alongside strict Clippy lints (`unwrap_used`, `expect_used`, `panic`, `indexing_slicing`, `arithmetic_side_effects`, and `missing_docs`).

---

## Workspace Crates

| Crate | Path | Responsibility |
| --- | --- | --- |
| `totaldrop-crypto` | `crates/totaldrop-crypto` | Suite `TD0` cryptographic primitives: domain-separated BLAKE3 `derive_key` contexts, CPace over `ristretto255` (`draft-irtf-cfrg-cpace`, SHA-512), Ed25519 + X25519 + post-quantum `ML-KEM-768` device identity certificates, `MailboxCipher` / `Sealer` / `Opener` channel AEAD, 4-word SAS verification indices, and `EntryCipher` 1 MiB STREAM chunk encryption (`ChaCha20-Poly1305`). |
| `totaldrop-proto` | `crates/totaldrop-proto` | Transport-independent protocol v0 rules: `TransferCode` generation, `parse`, `find`, and strict `from_link` share-URL parsing; deterministic RFC 8949 CBOR wire messages (`wire.rs`); relay challenge/batch/probe framing (`relay.rs`); PCP & NAT-PMP packet codecs (`portmap.rs`); and cross-platform NFC path safety validation (`SafePath`, `validate_path`). |
| `totaldrop-core` | `crates/totaldrop-core` | Async Tokio client engine: WebSocket rendezvous allocation/mailbox exchange, Noise `XXpsk3` + `ML-KEM-768` hybrid post-quantum handshake, QUIC over raw Ed25519 public keys (`quinn` + `rustls` RFC 7250), direct + STUN + relay racing, PCP/NAT-PMP/UPnP IGD port mapping with deterministic exit release, and resumable verified file/directory streaming. |
| `totaldrop-l10n` | `crates/totaldrop-l10n` | Compile-time embedded localization catalog (`l10n/app`, `l10n/cli`, `l10n/status.json`) across 35 languages + pseudo-locales (`en-XA`, `ar-XB`), BCP-47 locale negotiation, ICU message/plural formatting, RTL bidi isolation (`U+2068`…`U+2069`), regional SI byte formatting, and safety-critical draft translation gating. |

---

## Upstream `ebe2b19` Protocol & Security Updates

This standalone workspace incorporates all security and reliability fixes up through `ebe2b19`:

### 1. Strict Share-Link Parsing (`TransferCode::from_link` & `MAX_LINK_BYTES`)
- Implemented in `crates/totaldrop-proto/src/lib.rs` (`#445`):
  - Parses `https://totaldrop.app/r#…`, `http://totaldrop.app/r#…`, `totaldrop://r/…`, `totaldrop:…`, or a bare code.
  - Enforces a hard input cap of `MAX_LINK_BYTES = 1024` bytes before inspecting characters.
  - Strips invisible Unicode format/directional isolate marks (`INVISIBLE_FORMAT`: soft hyphen, ALM, ZWSP/ZWNJ/ZWJ, LRM/RLM, bidi embeddings/isolates, BOM) *before* prefix matching so leading marks copied from RTL chat apps cannot hide the URL scheme, and converts Arabic-Indic (`U+0660..=U+0669`) and Extended Arabic-Indic (`U+06F0..=U+06F9`) digits to ASCII.
  - Decodes `%XX` percent-escapes **strictly once** (preventing double-unescape ambiguity) and requires the entire remainder after the prefix to be a valid transfer code (rejecting trailing query parameters such as `?x`, extra path segments, or prose containing dates/numbers).

### 2. Broadcast, Multicast, and Special-Use `HINTS` Dial Guard (`#450`)
- Implemented in `crates/totaldrop-core/src/transport.rs` and `crates/totaldrop-core/src/lib.rs`:
  - Canonicalizes incoming peer socket addresses (unwrapping IPv4-mapped IPv6 `::ffff:a.b.c.d` and rejecting IPv4-compatible IPv6 addresses) before dialing candidate `public` and `local` endpoints announced in authenticated `HINTS`.
  - Refuses to dial IPv4 directed/limited broadcast (`255.255.255.255`), IPv4/IPv6 multicast (`224.0.0.0/4`, `ff00::/8`), unspecified (`0.0.0.0/8`, `::`), and port `0`, preventing a malicious peer who knows the transfer code from tricking the client into amplifying or spraying QUIC UDP packets onto local broadcast/multicast groups.

### 3. Port-Mapping Second Release Packet Completion on Exit (`#502`)
- Implemented in `crates/totaldrop-core/src/portmap.rs`:
  - `Release::send` transmits an immediate PCP/NAT-PMP zero-lifetime port-release UDP packet to the local gateway and schedules a second copy after `RESEND = 250 ms` to tolerate single-packet LAN loss.
  - The background resend task now holds a `Pending` token tracked by `released()`, so short-lived callers (such as the CLI exiting immediately after a transfer finishes) wait for the second release packet to go out (typically ~250 ms, bounded by `LIMIT = 1.6 s`) instead of tearing down the Tokio runtime early and leaving the router's port mapping open until lease expiry.

---

## Per-Architecture SIMD & Cryptographic Dispatch (`targets/`)

All workspace crates forbid `unsafe` code directly while delegating inner loops to audited RustCrypto (`chacha20poly1305`, `sha2`, `ml-kem`), Dalek (`curve25519-dalek`, `ed25519-dalek`), `blake3`, and `ring` backends that dispatch per-CPU SIMD and hardware cryptographic instructions.

| Profile File | Target Triple(s) | Key SIMD / Crypto Acceleration |
| --- | --- | --- |
| [`targets/x86_64.toml`](targets/x86_64.toml) | `x86_64-unknown-linux-gnu`, `x86_64-pc-windows-msvc`, `x86_64-apple-darwin`, `x86_64-linux-android` | Runtime CPUID dispatch for **AVX-512F/VL** (16-way BLAKE3 & ChaCha20), **AVX2** (8-way BLAKE3 & ChaCha20, SHA-512), **PCLMULQDQ** + **AES-NI** (`ring` QUIC/TLS 1.3), and 64-bit / AVX2 Curve25519 & ML-KEM-768 NTT vectorization (`x86-64-v3`). |
| [`targets/aarch64.toml`](targets/aarch64.toml) | `aarch64-unknown-linux-gnu`, `aarch64-apple-darwin`, `aarch64-linux-android` | Baseline 128-bit **ARMv8 NEON (ASIMD)** 4-way BLAKE3 & ChaCha20-Poly1305, plus **PMULL** carry-less multiply, **AES**, **SHA2** (`+sha2`), and ARMv8.2 **SHA-512** (`+sha3`) extensions (`apple-m1` / Linux `AT_HWCAP`). |
| [`targets/armv7.toml`](targets/armv7.toml) | `armv7-unknown-linux-gnueabihf`, `armv7-linux-androideabi` | **VFPv3 + NEON** ChaCha20/BLAKE3 vectorization (compile-time or Linux/Android `HWCAP_NEON` runtime probe in `ring`) and constant-time radix-$2^{25.5}$ `u32` scalar limbs (`UMULL`/`UMLAL`) in Curve25519/Ed25519. |
| [`targets/riscv64.toml`](targets/riscv64.toml) | `riscv64gc-unknown-linux-gnu` | Portable constant-time 64-bit `rv64gc` (`MUL`/`MULHU`) backend, with optional RVA22/RVA23 bit-manipulation (`+zba,+zbb,+zbs`), carry-less multiply (`+zbc` `CLMUL`), and **RVV 1.0** (`+v`) vectorization. |
| [`targets/wasm32-simd128.toml`](targets/wasm32-simd128.toml) | `wasm32-unknown-unknown` | Fixed-width 128-bit **Wasm SIMD128** (`+simd128`) 4-way `i32x4` BLAKE3 (`wasm32_simd`), vectorized ChaCha20/XChaCha20 & ML-KEM-768 for pure-Rust crates (`totaldrop-crypto`, `totaldrop-proto`, `totaldrop-l10n`), plus `getrandom` `0.4` opt-in `custom` / `wasm_js` CSPRNG support. |

Use `./targets/build-arch.sh` to inspect or invoke any architecture profile:

```sh
./targets/build-arch.sh x86_64-v3 --dry-run
./targets/build-arch.sh native --offline
```

---

## Building, Testing, and Linting

Requires Rust `1.99+` (`edition = "2024"`, `resolver = "3"`):

```sh
RUSTUP_TOOLCHAIN=stable cargo test --workspace --offline
RUSTUP_TOOLCHAIN=stable cargo clippy --workspace --all-targets --offline -- -D warnings
```

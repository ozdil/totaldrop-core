# Threat Model

This document defines what TotalDrop protects, against which adversaries, how
each threat is mitigated in code and formal proofs, and what residual risks
remain ahead of the pre-1.0 independent security audit.

Related documents: [protocol-v0.1-notes.md](protocol-v0.1-notes.md),
[accounts.md](accounts.md), and [decisions/0013-ghost-ring-accounts.md](decisions/0013-ghost-ring-accounts.md).

## 1. Protected Assets

| Asset | Protected Against | Current Status |
| --- | --- | --- |
| File contents, filenames, and folder hierarchy | Servers, network observers, and anyone without the one-time code or ring membership | Active (`CPace` + `Noise XXpsk3` + `ML-KEM-768` + `STREAM`) |
| Individual file sizes | Servers and network observers see total encrypted byte volume, not individual file boundaries | Active (padded/multiplexed inside encrypted QUIC/Relay stream) |
| User identity | Everyone: zero account required by default | Active; opt-in serverless Ghost Ring designed in [accounts.md](accounts.md) |
| Peer IP privacy | Remote peer when Privacy Mode (`--relay-only`) is enabled | Active |
| Receiver filesystem integrity | Malicious sender attempting path traversal, symlink escape, or file overwrite | Active (`totaldrop-proto` & `totaldrop-core` strict path confinement) |

## 2. Adversaries

1. **Active network attacker / MITM:** Reads, modifies, replays, or drops packets (public Wi-Fi, ISP, state-level censor).
2. **Malicious or compromised server:** Rendezvous Worker, Relay Worker, STUN server, or Cloudflare edge.
3. **Online code guesser:** Attempts to guess short transfer codes during the mailbox window.
4. **Malicious peer:** Possesses a valid transfer code and sends crafted manifests, oversized frames, or traversal paths.
5. **Store-now, decrypt-later quantum adversary:** Records encrypted traffic today to break classical ECDH later.
6. **Local same-machine / IPC attacker:** Sends malformed arguments, D-Bus requests, Share Extension manifests, or WinUI IPC frames.
7. **Supply-chain attacker:** Targets crate/npm dependencies, build containers, or unsigned release artifacts.
8. **Compromised or revoked Ghost Ring device / stolen recovery phrase / malicious contact (H1–H11):** Modeled formally in Tamarin (`totaldrop-formal-fuzz`) prior to Stage 1 & Stage 2 Ghost Ring rollout; see [accounts.md](accounts.md).

## 3. Core Defenses by Vulnerability Class

| Class | Defense |
| --- | --- |
| Memory unsafety | Safe Rust with `unsafe_code = "forbid"` across protocol, crypto, core, and server crates; minimal audited FFI boundaries on GUI bridges |
| Path traversal, symlink escape, overwrite | Allowlisted relative path segments, confinement beneath chosen destination folder, atomic non-overwriting file creation |
| DoS / resource exhaustion | Strict byte, frame, file-count, and timeout caps on wire parsers (`totaldrop-proto`), IPC decoders, and Durable Objects; continuous `cargo-fuzz` |
| Replay & downgrade | Ephemeral per-transfer keys; single protocol version & cipher suite (`TD0`), zero legacy fallback |
| Post-quantum & PAKE security | `CPace` (`ristretto255` + `SHA-512`), `Noise XXpsk3` (`X25519` + `ChaCha20-Poly1305` + `BLAKE2b`), `ML-KEM-768`, `Ed25519` (+ `ML-DSA-65` for Ghost Ring), `BLAKE3` |
| Web security (`totaldrop.app` & WASM) | Zero third-party scripts, strict CSP, `frame-ancestors 'none'`, HSTS, Subresource Integrity (`SRI`) |
| Supply chain & provenance | Locked dependencies (`Cargo.lock`, `--ignore-scripts`), `cargo-deny`, `REUSE 3.3`, reproducible `SOURCE_DATE_EPOCH` builds, Sigstore keyless attestations (`*.sigstore.json`) |
| Secret hygiene | Release keys & `CLOUDFLARE_API_TOKEN` isolated inside approval-gated GitHub Environments; `gitleaks` CI gate on every push and PR |

## 4. Out of Scope

- **Compromised endpoint OS:** Malware running as the user can read files before encryption or after decryption.
- **Malicious payload inside transferred files:** TotalDrop transports bytes faithfully without scanning user files; receivers choose whether to accept and open files.
- **Traffic existence & total byte volume:** Network observers can tell an encrypted session occurred and its approximate total size.

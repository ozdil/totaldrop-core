# Engineering and Release Process

All GitHub issues, pull requests, code reviews, discussions, commit messages,
and documentation across the `totaldrop-app` organization are conducted **100% in
English** ([0019](decisions/0019-english-by-default.md)) so our growing
international team collaborates on a single source of truth.

## 1. Workflow

1. **Issue First:** Every non-trivial change starts with an English GitHub issue
   in the target repository (`totaldrop-core`, `totaldrop-linux`, etc.) linked
   to a milestone (`Now`, `Next`, `Later`, `1.0`) and labeled by area and
   architecture (`arch:x86_64`, `arch:arm64`, `arch:riscv64`, `area:l10n`, etc.).
2. **Short-Lived Branch:** Branch names state intent (`feat/ring-mailbox`,
   `fix/linux-quit-portmap`, `pkg/linux-deb-riscv64`).
3. **Pull Request & CI Gate:** Every PR links its issue (`Closes #...`) and
   passes the required `CI` gate job (formatting, `clippy -- -D warnings`, unit
   & integration tests, cross-target checks, `cargo-deny`, `REUSE 3.3`, and
   `gitleaks` secret scan). Red checks are never bypassed.
4. **Independent Review:** Every PR affecting code, cryptography, protocol, CI,
   packaging recipes, or security documents is reviewed by a maintainer or an
   independent review session that did not author the diff.
5. **Linear History:** Pull requests merge via rebase onto `main`; force-pushes
   to `main` are disabled.

## 2. Definition of Done

A change is complete only when all of the following hold:
- Behavioral tests cover both happy paths and specific error variants (no
  fixed-sleep flaky assertions; use bounded condition polling).
- State machines use explicit typed `enum` states and generation counters across
  `await` boundaries — never implicit boolean pairs.
- Every new parser of untrusted bytes/JSON/IPC frames has a `cargo-fuzz` target
  in `totaldrop-formal-fuzz`.
- Untrusted peer text (filenames, device names, error details) is sanitized
  against terminal/UI control and invisible Bidi characters in a single pass.
- Protocol changes update [protocol-v0.1-notes.md](protocol-v0.1-notes.md);
  architectural changes add or update a record in [decisions/](decisions/README.md).
- User-facing string changes update `totaldrop-core/l10n/` (`en` template first,
  respecting `l10n/status.json` security-critical review gating; see
  [translation.md](translation.md)).
- Any change to what servers observe updates the 35-language privacy policy in
  `totaldrop-site` **before** release.

## 3. Sub-Platform × Architecture Releases

Each sub-platform × CPU unit (`subplatforms/<format>/<arch>/`) builds in an
isolated container/VM with `SOURCE_DATE_EPOCH`, verifies package contents and
smoke startup, generates `SHA256SUMS`, and attaches a keyless Sigstore build
provenance bundle (`*.sigstore.json`) verifiable via `gh attestation verify`.

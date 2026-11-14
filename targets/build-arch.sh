#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 The TotalDrop Contributors
# SPDX-License-Identifier: MIT OR Apache-2.0
#
# Per-architecture build driver for TotalDrop 00-core.
#
# Usage:
#   ./targets/build-arch.sh <profile> [--dry-run] [--offline]
#
# Profiles:
#   native          Host architecture build using portable baseline flags
#   x86_64          x86_64-unknown-linux-gnu (baseline + runtime AVX2/AVX-512/PCLMULQDQ)
#   x86_64-v3       x86_64-unknown-linux-gnu (-C target-cpu=x86-64-v3 +pclmulqdq,+aes)
#   aarch64         aarch64-unknown-linux-gnu (+neon,+aes,+pmull,+sha2)
#   armv7           armv7-unknown-linux-gnueabihf (+vfp3,+neon)
#   riscv64         riscv64gc-unknown-linux-gnu (generic-rv64)
#   wasm32-simd128  wasm32-unknown-unknown (+simd128, pure-Rust crates only)

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROFILE="${1:-native}"
shift || true

DRY_RUN=0
EXTRA_CARGO_ARGS=()
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    *) EXTRA_CARGO_ARGS+=("$arg") ;;
  esac
done

if [[ -z "${RUSTUP_TOOLCHAIN:-}" ]] && ! rustup show active-toolchain >/dev/null 2>&1; then
  export RUSTUP_TOOLCHAIN="stable"
fi

PACKAGES=("--workspace")
case "$PROFILE" in
  native)
    TARGET_TRIPLE=""
    ARCH_RUSTFLAGS=""
    ;;
  x86_64)
    TARGET_TRIPLE="x86_64-unknown-linux-gnu"
    ARCH_RUSTFLAGS="-C target-cpu=x86-64"
    ;;
  x86_64-v3)
    TARGET_TRIPLE="x86_64-unknown-linux-gnu"
    ARCH_RUSTFLAGS="-C target-cpu=x86-64-v3 -C target-feature=+pclmulqdq,+aes"
    ;;
  aarch64)
    TARGET_TRIPLE="aarch64-unknown-linux-gnu"
    ARCH_RUSTFLAGS="-C target-feature=+neon,+aes,+pmull,+sha2"
    ;;
  armv7)
    TARGET_TRIPLE="armv7-unknown-linux-gnueabihf"
    ARCH_RUSTFLAGS="-C target-feature=+vfp3,+neon"
    ;;
  riscv64)
    TARGET_TRIPLE="riscv64gc-unknown-linux-gnu"
    ARCH_RUSTFLAGS="-C target-cpu=generic-rv64"
    ;;
  wasm32-simd128)
    TARGET_TRIPLE="wasm32-unknown-unknown"
    ARCH_RUSTFLAGS="-C target-feature=+simd128 --cfg getrandom_backend=\"custom\""
    PACKAGES=("-p" "totaldrop-crypto" "-p" "totaldrop-proto" "-p" "totaldrop-l10n")
    ;;
  *)
    echo "Unknown architecture profile: $PROFILE" >&2
    echo "Expected one of: native, x86_64, x86_64-v3, aarch64, armv7, riscv64, wasm32-simd128" >&2
    exit 2
    ;;
esac

CMD=(cargo build --release "${PACKAGES[@]}")
if [[ -n "$TARGET_TRIPLE" ]]; then
  CMD+=(--target "$TARGET_TRIPLE")
fi
if [[ ${#EXTRA_CARGO_ARGS[@]} -gt 0 ]]; then
  CMD+=("${EXTRA_CARGO_ARGS[@]}")
fi

echo "Profile:        $PROFILE"
echo "Toolchain:      ${RUSTUP_TOOLCHAIN:-$(rustup show active-toolchain | awk '{print $1}')}"
echo "Target triple:  ${TARGET_TRIPLE:-<host default>}"
echo "RUSTFLAGS:      ${ARCH_RUSTFLAGS:-<none>}"
echo "Command:        RUSTFLAGS=\"$ARCH_RUSTFLAGS\" ${CMD[*]}"

if [[ "$DRY_RUN" -eq 1 ]]; then
  exit 0
fi

if [[ -n "$TARGET_TRIPLE" ]]; then
  INSTALLED_TARGETS="$(rustup target list --installed 2>/dev/null || true)"
  if ! grep -qx "$TARGET_TRIPLE" <<<"$INSTALLED_TARGETS"; then
    echo "error: Rust target '$TARGET_TRIPLE' is not installed in toolchain '${RUSTUP_TOOLCHAIN:-active}'." >&2
    echo "Install it first with: rustup target add $TARGET_TRIPLE" >&2
    exit 1
  fi
fi

cd "$ROOT_DIR"
RUSTFLAGS="${ARCH_RUSTFLAGS}${RUSTFLAGS:+ $RUSTFLAGS}" "${CMD[@]}"

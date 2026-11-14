# TotalDrop Name and Köşe Mark Policy

As established in [0012](decisions/0012-name-and-mark.md), all TotalDrop source
code is free and open source (`MIT OR Apache-2.0` for libraries, CLI, and
servers; `GPL-3.0-or-later` for applications and the website; see `LICENSING.md`
and `REUSE.toml`), while the **TotalDrop** name, the `app.totaldrop.*`
application identifiers, `totaldrop.app`, and the **Köşe** mark (a circle with
its top-right corner squared) identify official releases built and attested by
the TotalDrop project.

## Permitted Uses Without Special Permission

1. **Unmodified Redistribution & Packaging:** Linux distributions, BSD ports,
   F-Droid, Flathub, Homebrew, WinGet, and Nixpkgs may build and distribute
   unmodified TotalDrop releases (plus standard distribution build/dependency
   patches that do not alter protocol security, cryptography, or privacy
   behavior) under the **TotalDrop** name and Köşe mark.
2. **Descriptive Reference:** Stating truthfully that software interoperates
   with or is derived from TotalDrop.

## Forks and Modified Versions

If you distribute a modified version or fork with custom servers, altered
cryptography/telemetry, or independent branding, you must replace the name
`TotalDrop`, the `app.totaldrop.*` bundle IDs, and the Köşe mark so users know
whose build they are trusting.

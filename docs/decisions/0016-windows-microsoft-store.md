# 0016: The Windows app uses WinUI 3 and ships through Microsoft Store and native packages

- **Status:** Accepted, 10 November 2026 (Ozan, #33); modular sub-platform
  packaging expanded in [0020](0020-modular-subplatform-matrix.md).
- **Context:** Windows support (#33) required choosing a native UI toolkit
  that matches Windows 11 system visuals 100% ([design.md](../design.md))
  and solving SmartScreen / Defender code-signing trust without recurring
  certificate lock-in. Microsoft Store individual and company developer
  registration became free (`storedeveloper.microsoft.com`), and MSIX
  submissions are signed by Microsoft after certification.
- **Options:**
  1. **Qt 6 and QML.** Shares Linux UI code, but `FluentWinUI3` only
     approximates Mica, title-bar integration, system accent color, and high
     contrast.
  2. **Flutter Windows desktop.** Shares Android Dart code, but Material UI
     looks foreign on Windows.
  3. **WinUI 3 (Windows App SDK) over the Rust C/IPC bridge.** Native Fluent
     controls, light/dark/high-contrast themes, system accent color, Segoe UI
     Variable, Fluent icons, `MicaBackdrop`, and `ExtendsContentIntoTitleBar`.
- **Decision:** Option 3 (`totaldrop-windows`).
  - All protocol, cryptography, and transfer state machines remain strictly in
    Rust (`totaldrop-core`, `totaldrop-proto`, `totaldrop-crypto`). The UI
    layer never implements cryptography.
  - Sub-platform × CPU architecture units (`msix`, `winget`, `portable-zip` ×
    `x86_64`, `arm64`) build and verify independently in CI
    ([0020](0020-modular-subplatform-matrix.md)).
  - All 35 languages ([0008](0008-languages-and-regions.md)) compile from the
    single ARB source into `.resw` string tables, with `FlowDirection` RTL
    mirroring for `ar`, `fa`, `he`, and `ur` while keeping transfer codes and
    SAS verification words LTR.
  - Reduced motion follows `UISettings.AnimationsEnabled`; UI Automation names,
    keyboard navigation, high contrast, and text scaling up to 225% are
    mandatory gates.

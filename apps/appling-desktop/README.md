# Appling desktop installers

This is a dedicated launcher for Appling's browser UI. The separate app in
`apps/desktop` is the Hermes chat client and must not be packaged as Appling.

The DMG, NSIS installer, and AppImage include the Appling source tree, its
prebuilt UI, platform-specific `uv`, Node.js and npm. On first launch the app copies
the source to its application-data folder, installs Python 3.11 and locked
dependencies, enables the Ultimate Builder plugin, then opens Appling in its
own window. First launch needs an internet connection. Later launches reuse
the installed runtime. Project files remain in the folders selected by users,
with `~/Appling Projects` as the default; they are never stored inside the
application bundle.

## Build on each target OS

```bash
cd lyra_lite/ui && npm ci && npm run build
cd ../../apps/appling-desktop && npm ci --workspaces=false
npm run dist:mac    # macOS: DMG
npm run dist:win    # Windows: NSIS
npm run dist:linux  # Linux: AppImage
```

Only run the matching target command on its own OS. The workflow
`.github/workflows/appling-installers.yml` builds all three on native runners
and uploads them as workflow artifacts. Package versions and `lyra_lite`
versions must be advanced together for each Appling release. This first beta
packaging is unsigned; sign and notarize the macOS DMG and sign the Windows
installer before calling the downloads ready for nontechnical users.

The runtime is versioned under the app-data directory. Replacing an installer
does not modify a user's project folders. First-launch logs are written to
`appling-startup.log` in the app-data directory.

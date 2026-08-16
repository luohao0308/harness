# Harness Runtime Assets

Release builds place the native `harnessd` sidecar at
`<platform>/<arch>/harnessd` (`harnessd.exe` on Windows), with a sibling
`runtime-manifest.json`, before electron-builder runs. The manifest contains schema
version, runtime version, Node platform/architecture names, executable name, and the
lowercase SHA-256 digest. Electron resolves this directory through `process.resourcesPath`; mutable data
is always written under Electron's per-user `userData/runtime` directory.

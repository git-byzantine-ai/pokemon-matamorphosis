# Build the Windows portable release

Build on Windows x64 with Python 3.12 and the pinned build dependencies. The
packaged app does not require Python, Git, MSYS2 or Codex on the player's PC.

```powershell
python -m venv .tools/packaging-venv
.tools/packaging-venv/Scripts/python.exe -m pip install -r packaging/requirements-build.txt
```

Prepare the verified baseline and patched ROM using the repository's Windows
build instructions. For this release the patched bundle is `build/triple-update`:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/build.ps1 -Baseline
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/build.ps1 -OutputDirectory build/triple-update
.tools/packaging-venv/Scripts/python.exe scripts/build_portable.py --bundle build/triple-update
.tools/packaging-venv/Scripts/python.exe -m unittest discover -s tests -p test_portable.py -v
```

The output is `dist/Pokemon-Metamorphosis-<version>-Windows-x64.zip` and its
`.sha256` file. Update `portable/__init__.py` for subsequent versions. The builder
verifies the baseline, verifies the IPS output against the bridge manifest, and
locates compressed reference graphics in the baseline ROM. Only offsets/catalog
metadata are packaged; setup extracts the graphics from the player's ROM.

Do not publish development `build/`, `runtime/`, `.tools/`, saves, original ROMs,
model weights, or reference PNGs. The ZIP allowlist is the PyInstaller application,
release patch/metadata, player guide and third-party notices. The builder rejects
ROM/save/database/model extensions in the finished archive.

Before publishing, extract into a new directory, remove developer tools from PATH,
run setup, Test AI, and Play, then load the bridge in mGBA. Test updates with a copy
of save/history data and verify normal saves survive. Keep the signed-off ZIP's
checksum with the release notes. The current executable is unsigned.

CLI verification modes (the graphical interface is the player-facing default):

```powershell
.\Metamorphosis.exe --setup --rom C:\Games\FireRed.gba --data-dir C:\TestData --report C:\setup.json
.\Metamorphosis.exe --test-ai --data-dir C:\TestData --report C:\ai.json
.\Metamorphosis.exe --verify --data-dir C:\TestData --report C:\verify.json
```

Optional `--model-file` imports a model after verifying its pinned SHA-256. It is
not an unverified model override. A progress sidecar `<report>.progress` is written
for automated checks. CLI exit codes are meaningful; wait for the GUI-subsystem
process to finish when running automated checks.

Publish the ZIP and checksum as a GitHub prerelease. The repository source archive
is for developers; players should download the Windows ZIP asset.

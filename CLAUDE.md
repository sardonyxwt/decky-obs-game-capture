# CLAUDE.md — project context

A Decky Loader plugin for Steam's Game Mode on Linux (gamescope-session). Goal: stream games with OBS without manual
setup — one button installs OBS (flatpak) + obs-vkcapture + the Vulkan layer and configures OBS; one toggle puts
`OBS_VKCAPTURE=1` into every game's launch options, new games included. README.md describes the behaviour.

## Built on
- Ubuntu 26.04 + gamescope-session, native Steam (`~/.steam/debian-installation`), Decky Loader
- GPU: AMD Radeon RX 9060 XT (renderD129) + Intel iGPU (renderD128), display 2560×1440

## Layout
- `main.py` — Decky backend (`Plugin`): `get_state`, `start_setup` (background task, ends with the
  `obs_setup_finished` event), `save_games` (records what the frontend did to launch options), `set_virtual_mic`, `get_artwork`
- `py_modules/obscapture/` — logic without Decky (standard library only):
  - `flatpak.py` — flatpak CLI, always `--user`; `install` uses `--or-update`
  - `layer.py` — copies `libVkLayer_obs_vkcapture.so` (64 + 32 bit) from the flatpak extension to
    `<runtime>/vkcapture/<multiarch>/` and writes manifests to `~/.local/share/vulkan/implicit_layer.d/` with
    `library_path` pointing there; a system obs-vkcapture (in /usr/share) wins. `remove` touches only manifests that
    point into the plugin's folder
  - `obsconfig.py` — edits the flatpak OBS config in `~/.var/app/com.obsproject.Studio/config/obs-studio`: profile
    `basic.ini` (Advanced output, encoder, canvas/output/FPS), `streamEncoder.json`, `service.json` (only if missing),
    scene collection JSON (adds a `vkcapture-source` item on top). Names come from `user.ini` `[Basic]` (OBS 31+),
    else `global.ini`. Backups `*.obs-game-capture.bak` once
  - `system.py` — OBS running (`/proc/*/comm == obs`), render node (boot_vga first, Intel last), display size
  - `virtualmic.py` — the "Virtual microphone" toggle: a silent `Audio/Source/Virtual` null sink (priority.session
    1500: above outputs' monitors, below real mics) as a PipeWire drop-in in `~/.config/pipewire/pipewire.conf.d/` plus
    a live node via `pw-cli create-node` (`object.linger`). Without any source Steam's Settings → Audio crashes
  - `artwork.py` — OBS's Steam store art (app 1905180) for kinds the shortcut has no grid image of
- `src/` — frontend (React, @decky/ui, @decky/api)
  - `launchOptions.ts` — pure add/remove of the flag (at the start of the line: env assignments must precede the command)
  - `steam.ts` — launch options through `SetAppLaunchOptions`, the OBS shortcut (`AddShortcut` + quoted exe/dir like
    the user's other shortcuts, `SpecifyCompatTool(id, "")`), icon, `SetCustomArtworkForApp`
  - `index.tsx` — panel; sweep at load and every 60 s while enabled; `i18n.ts` — `t(english, russian)`

## Commands
```bash
pnpm install && pnpm run typecheck && pnpm run build
python3 tests/test_backend.py
O=$(mktemp -d) && npx tsc src/launchOptions.ts --outDir $O --module es2020 --target es2020 --skipLibCheck --typeRoots ./none && node tests/launchOptions.test.mjs $O
./scripts/package.sh
./scripts/deploy.sh user@host
```

## Rules
- Python: standard library only (Decky's PyInstaller Python). Clear `LD_LIBRARY_PATH` for external tools (`flatpak.clean_env`).
- Generic plugin: nothing tied to one machine in the code.
- Never touch an existing stream service / stream key. Never edit OBS files while OBS runs.
- State: `settings/settings.json` — `enabled`, `applied` (appids the plugin added the flag to; only those lose it on
  disable), `layer_registered`. While enabled, every sweep checks every target and re-adds a missing flag.
- Launch options are read only through `RegisterForAppDetails`: `appDetailsStore` keeps stale values for apps whose
  page is not open, and writing back from them drops the user's options.
- `_uninstall` is also called on plugin updates: it removes the layer and the virtual microphone, and `_main` puts them
  back when `layer_registered` / `virtual_mic` are set.

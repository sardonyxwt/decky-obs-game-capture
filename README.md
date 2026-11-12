# OBS Game Capture — a Decky Loader plugin

Stream or record games from Steam's Game Mode with OBS Studio, without setting anything up by hand.
One button installs and configures OBS, one toggle makes every game capturable. The UI follows Steam's
language (English or Russian).

## What it does

**Install and set up** (the button in the panel; safe to press again, it updates and repairs):

1. Adds Flathub for the user and installs **OBS Studio** (`com.obsproject.Studio`) unless OBS is installed already.
   Everything goes into the user's flatpak installation: no root, no password.
2. Installs the **obs-vkcapture** OBS plugin (`com.obsproject.Studio.Plugin.OBSVkCapture`): the "Game Capture"
   source that takes frames straight from a game's Vulkan swapchain. Under gamescope this is the capture that works;
   screen capture through the desktop portal does not exist in Game Mode.
3. Installs the **Vulkan capture layer** (`org.freedesktop.Platform.VulkanLayer.OBSVkCapture`, the newest branch, plus
   the branch flatpak Steam uses if it is installed) and registers it for games outside flatpak: its library (it
   needs only libc) is copied to the plugin's data folder and a manifest goes to
   `~/.local/share/vulkan/implicit_layer.d/`. If the distribution already ships obs-vkcapture (Bazzite, Arch), that
   one is used and nothing is copied. The layer stays idle in a game unless the game starts with `OBS_VKCAPTURE=1`.
4. **Sets OBS up for streaming** (only while OBS is closed — it rewrites its files on exit):
   - a **Game Capture** source on top of the current scene, scaled to fill the canvas (other sources stay);
   - canvas = the display's resolution, output scaled to 1080p (or the display's size if smaller), 60 FPS;
   - hardware encoding: VA-API H.264 on AMD and Intel on the GPU that drives the display (`/dev/dri/renderD*` is chosen
     explicitly, as with an iGPU + dGPU renderD128 is often the iGPU); x264 elsewhere. CBR 6000 kbps, keyframe every
     2 s, 160 kbps audio — Twitch's recommendations. OBS shows VA-API only in its Advanced output mode, so the profile
     is switched to it;
   - the stream service is set to Twitch only when none is configured; an existing service and its stream key are
     never touched. The stream key is yours to enter (OBS → Settings → Stream).
   The first time a file is changed, its original is kept as `*.obs-game-capture.bak` next to it.
5. Adds **OBS Studio** to the Steam library as a non-Steam app (`flatpak run com.obsproject.Studio`, no Proton) with
   its icon and the library artwork from OBS Studio's Steam store page, unless such a shortcut exists.

**Capture flag in every game** (the toggle):

- On: adds `OBS_VKCAPTURE=1` to the launch options of every installed Steam game and every non-Steam game (OBS's own
  shortcut excepted). Games installed or added later get it within a minute, and at every Steam start.
- The flag goes in front of everything else (`OBS_VKCAPTURE=1 gamemoderun %command% -dx11`); other launch options and
  other plugins' wrappers stay. Games with only arguments (`-dx11`) get `%command%` added in front of them.
- While it is on, every game keeps the flag: if something takes it out (you, another tool), it is back within a minute.
- Off: takes the flag out of every game the plugin put it into; a flag you had added yourself before is left alone.

Then: start OBS from the library, start the game, and switch between them with the Steam button. Proton games
(DXVK / VKD3D) and native Vulkan games are captured; native OpenGL games are not (they would need obs-glcapture's
`LD_PRELOAD`, which this plugin does not set).

**Virtual microphone** (the toggle in the Audio section, off by default):

- When no microphone is connected, WirePlumber makes the monitor of an output the default input and Steam's
  Settings → Audio page fails with "An error occurred while rendering this content". The toggle adds a silent PipeWire
  source, "virtual-microphone", that Steam then uses as its input device.
- It is written to `~/.config/pipewire/pipewire.conf.d/90-obs-game-capture-virtual-mic.conf`, so it is back after
  every reboot, and created right away with `pw-cli` (no PipeWire restart). Its session priority (1500) is above every
  output and below real microphones: a connected microphone still becomes the default input.
- Off removes the file and the source.

## Removing

Turn the toggle off first, then uninstall the plugin in Decky: the layer manifests and the copied library are
removed, and so is the virtual microphone. OBS, its plugin and settings stay (uninstall them with `flatpak uninstall --user com.obsproject.Studio`).
A flag left in a game's launch options does nothing without the layer.

## Building

```bash
pnpm install
pnpm run typecheck
pnpm run build                    # → dist/index.js
python3 tests/test_backend.py     # backend tests (no network, temp folders)
./scripts/package.sh              # → out/obs-game-capture.zip for Decky's "Install plugin from ZIP"
./scripts/deploy.sh user@host     # build and install on a Steam machine over SSH (no sudo needed)
```

## License

BSD-3-Clause. OBS Studio and obs-vkcapture are GPL-2.0 and are installed from Flathub, not shipped with the plugin.

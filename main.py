import asyncio
import json
import os
import traceback

import decky  # provided by Decky Loader

from obscapture import artwork, flatpak, layer, obsconfig, system, virtualmic

SETTINGS = "settings.json"
DEFAULT_SETTINGS = {
    "enabled": False,  # OBS_VKCAPTURE=1 goes into every game's launch options
    "applied": [],     # appids whose launch options the plugin changed (taken out again on disable)
    "virtual_mic": False,  # a silent PipeWire microphone for when none is connected
}
FALLBACK_CANVAS = (1920, 1080)
# setup steps in order; the frontend shows their names
STEPS = ("flathub", "obs", "vkcapture", "layer", "obs_config")


def _err(e: Exception) -> dict:
    decky.logger.error("".join(traceback.format_exception(e)))
    return {"ok": False, "error": str(e)}


class Plugin:
    # ---------------- lifecycle ----------------
    async def _main(self):
        self.home = decky.DECKY_USER_HOME
        self.env = flatpak.clean_env(self.home)
        self.layer_dest = os.path.join(decky.DECKY_PLUGIN_RUNTIME_DIR, "vkcapture")
        self.settings_path = os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, SETTINGS)
        os.makedirs(decky.DECKY_PLUGIN_SETTINGS_DIR, exist_ok=True)
        self.setup_task = None
        self.setup_state = {"running": False, "step": "", "done": [], "errors": {}, "obs_config": None}
        # Decky calls _uninstall on updates too, which removes the layer: put it back from the installed
        # extension whenever setup has registered it before (this also picks up extension updates).
        if self._settings().get("layer_registered"):
            try:
                await asyncio.get_running_loop().run_in_executor(None, self._register_layer)
            except Exception as e:  # noqa: BLE001
                decky.logger.error(f"could not re-register the layer: {e}")
        # _uninstall (also run on updates) removes the microphone too
        if self._settings().get("virtual_mic"):
            try:
                await asyncio.get_running_loop().run_in_executor(None, virtualmic.enable, self.home, self.env)
            except Exception as e:  # noqa: BLE001
                decky.logger.error(f"could not restore the virtual microphone: {e}")
        decky.logger.info("OBS Game Capture backend started")

    async def _unload(self):
        if self.setup_task:
            self.setup_task.cancel()

    async def _uninstall(self):
        # The flag left in launch options is harmless without the layer.
        try:
            layer.remove(decky.DECKY_USER_HOME, os.path.join(decky.DECKY_PLUGIN_RUNTIME_DIR, "vkcapture"))
        except Exception as e:  # noqa: BLE001
            decky.logger.error(f"uninstall: {e}")
        try:
            virtualmic.disable(decky.DECKY_USER_HOME, flatpak.clean_env(decky.DECKY_USER_HOME))
        except Exception as e:  # noqa: BLE001
            decky.logger.error(f"uninstall: {e}")

    # ---------------- helpers ----------------
    def _settings(self) -> dict:
        s = dict(DEFAULT_SETTINGS)
        try:
            with open(self.settings_path, encoding="utf-8") as f:
                s.update(json.load(f))
        except (OSError, ValueError):
            pass
        return s

    def _save(self, **changes) -> dict:
        s = self._settings()
        s.update(changes)
        with open(self.settings_path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(s, f, indent=1)
        os.replace(self.settings_path + ".tmp", self.settings_path)
        return s

    def _register_layer(self) -> None:
        if layer.system_layer():
            return
        rows = flatpak.installed(self.env)
        ext = flatpak.find(rows, flatpak.VKCAPTURE_LAYER)
        if not ext:
            raise layer.LayerError("the OBSVkCapture Vulkan layer extension is not installed")
        loc = flatpak.location(f"runtime/{flatpak.VKCAPTURE_LAYER}/x86_64/{ext['branch']}", self.env)
        if not loc:
            raise layer.LayerError("could not find the Vulkan layer extension's files")
        layer.install(os.path.join(loc, "files"), self.home, self.layer_dest)

    def _status_blocking(self) -> dict:
        rows = flatpak.installed(self.env)
        obs = flatpak.find(rows, flatpak.OBS)
        plugin = flatpak.find(rows, flatpak.VKCAPTURE_PLUGIN)
        icon = ""
        if obs:
            base = (os.path.join(self.home, ".local/share/flatpak") if obs["installation"] == "user"
                    else "/var/lib/flatpak")
            p = os.path.join(base, "exports/share/icons/hicolor/256x256/apps", f"{flatpak.OBS}.png")
            icon = p if os.path.isfile(p) else ""
        return {
            "flatpak": flatpak.available(self.env),
            "obs": obs,
            "vkcapture": plugin,
            "layer": layer.status(self.home, self.layer_dest),
            "obs_configured": obsconfig.configured(self.home),
            "obs_running": system.obs_running(),
            "virtual_mic_running": virtualmic.running(self.env),
            "icon": icon,
            "home": self.home,
        }

    def _step(self, name: str, fn) -> bool:
        self.setup_state["step"] = name
        try:
            result = fn()
            if name == "obs_config":
                self.setup_state["obs_config"] = result
            self.setup_state["done"].append(name)
            return True
        except Exception as e:  # noqa: BLE001
            decky.logger.error(f"setup step {name}: {''.join(traceback.format_exception(e))}")
            self.setup_state["errors"][name] = str(e)
            return False

    def _setup_blocking(self) -> None:
        env = self.env
        if not self._step("flathub", lambda: flatpak.ensure_flathub(env)):
            return

        def install_obs():
            rows = flatpak.installed(env)
            if not flatpak.find(rows, flatpak.OBS):  # a system-wide OBS is fine as it is
                flatpak.install([flatpak.OBS], env)

        if not self._step("obs", install_obs):
            return
        self._step("vkcapture", lambda: flatpak.install([flatpak.VKCAPTURE_PLUGIN], env))

        def install_layer():
            # newest branch for native games; flatpak Steam's games see only the branch of its own runtime
            branches = flatpak.remote_branches(flatpak.VKCAPTURE_LAYER, env)
            if not branches:
                raise flatpak.FlatpakError("Flathub has no OBSVkCapture Vulkan layer")
            wanted = {branches[-1]}
            steam = flatpak.runtime_branch(flatpak.FLATPAK_STEAM, env)
            if steam in branches:
                wanted.add(steam)
            flatpak.install([f"{flatpak.VKCAPTURE_LAYER}//{b}" for b in sorted(wanted)], env)
            self._register_layer()
            self._save(layer_registered=True)

        self._step("layer", install_layer)

        def configure_obs():
            if system.obs_running():
                raise RuntimeError("OBS is running: close it and run setup again")
            canvas = system.display_size() or FALLBACK_CANVAS
            return obsconfig.configure(self.home, canvas, system.render_node())

        self._step("obs_config", configure_obs)

    async def _run_setup(self):
        try:
            await asyncio.get_running_loop().run_in_executor(None, self._setup_blocking)
        finally:
            self.setup_state["running"] = False
            self.setup_state["step"] = ""
            await decky.emit("obs_setup_finished", self.setup_state)

    # ---------------- frontend API ----------------
    async def get_state(self) -> dict:
        try:
            status = await asyncio.get_running_loop().run_in_executor(None, self._status_blocking)
            s = self._settings()
            return {"ok": True, **status, "enabled": s["enabled"], "applied": s["applied"],
                    "virtual_mic": s["virtual_mic"], "setup": self.setup_state}
        except Exception as e:  # noqa: BLE001
            return _err(e)

    async def start_setup(self) -> dict:
        if self.setup_state["running"]:
            return {"ok": True, "already": True}
        self.setup_state = {"running": True, "step": "", "done": [], "errors": {}, "obs_config": None}
        self.setup_task = asyncio.get_running_loop().create_task(self._run_setup())
        return {"ok": True}

    async def save_games(self, enabled: bool, applied: list) -> dict:
        """The frontend changes launch options (only Steam can) and records here what it did."""
        try:
            self._save(enabled=bool(enabled), applied=sorted({int(a) for a in applied}))
            return {"ok": True}
        except Exception as e:  # noqa: BLE001
            return _err(e)

    async def set_virtual_mic(self, enabled: bool) -> dict:
        try:
            fn = virtualmic.enable if enabled else virtualmic.disable
            await asyncio.get_running_loop().run_in_executor(None, fn, self.home, self.env)
            self._save(virtual_mic=bool(enabled))
            return {"ok": True}
        except Exception as e:  # noqa: BLE001
            return _err(e)

    async def get_artwork(self, appid: int) -> dict:
        """OBS's store artwork for the kinds the shortcut has no custom image of."""
        try:
            loop = asyncio.get_running_loop()
            kinds = await loop.run_in_executor(None, artwork.missing_kinds, self.home, int(appid))
            images = await loop.run_in_executor(None, artwork.download, kinds)
            return {"ok": True, "images": images}
        except Exception as e:  # noqa: BLE001
            return _err(e)

"""The obs-vkcapture Vulkan layer for games that run outside flatpak (native Steam, Proton).

Flathub ships the layer only as a flatpak extension, which only flatpak apps see. Its library needs nothing but
libc, so the plugin copies it to its own data folder and registers it as a user implicit layer in
~/.local/share/vulkan/implicit_layer.d. The layer stays idle unless a game starts with OBS_VKCAPTURE=1.
Distributions that package obs-vkcapture (Bazzite, Arch) already have it in /usr/share: then nothing is copied.
"""

import json
import os
import shutil
from typing import Optional

# json file name -> multiarch folder of the library inside the extension
ARCHES = {"obs_vkcapture_64.json": "x86_64-linux-gnu", "obs_vkcapture_32.json": "i386-linux-gnu"}
LIBRARY = "libVkLayer_obs_vkcapture.so"
SYSTEM_DIRS = ("/usr/share/vulkan/implicit_layer.d", "/usr/local/share/vulkan/implicit_layer.d",
               "/etc/vulkan/implicit_layer.d")


class LayerError(Exception):
    pass


def user_layer_dir(home: str) -> str:
    data = os.environ.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share")
    return os.path.join(data, "vulkan", "implicit_layer.d")


def system_layer(system_dirs=SYSTEM_DIRS) -> Optional[str]:
    for d in system_dirs:
        p = os.path.join(d, "obs_vkcapture_64.json")
        if os.path.isfile(p):
            return p
    return None


def _read(path: str) -> Optional[dict]:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _library_path(manifest: Optional[dict]) -> str:
    return ((manifest or {}).get("layer") or {}).get("library_path") or ""


def status(home: str, dest: str, system_dirs=SYSTEM_DIRS) -> Optional[str]:
    """'system' (a distribution package), 'plugin' (registered by this plugin) or None."""
    if system_layer(system_dirs):
        return "system"
    p = os.path.join(user_layer_dir(home), "obs_vkcapture_64.json")
    lib = _library_path(_read(p))
    if lib.startswith(dest + os.sep) and os.path.isfile(lib):
        return "plugin"
    return None


def _copy_atomic(src: str, dst: str) -> None:
    # A new inode: a game that has the old library mapped keeps running.
    tmp = dst + ".tmp"
    shutil.copyfile(src, tmp)
    os.chmod(tmp, 0o755)
    os.replace(tmp, dst)


def install(ext_files: str, home: str, dest: str) -> None:
    """Copies the layer from the flatpak extension's files folder to dest and registers it for the user."""
    layer_dir = user_layer_dir(home)
    os.makedirs(layer_dir, exist_ok=True)
    done = 0
    for name, arch in ARCHES.items():
        manifest = _read(os.path.join(ext_files, "share", "vulkan", "implicit_layer.d", name))
        src = os.path.join(ext_files, "lib", arch, LIBRARY)
        if not manifest or not os.path.isfile(src):
            continue
        os.makedirs(os.path.join(dest, arch), exist_ok=True)
        lib = os.path.join(dest, arch, LIBRARY)
        _copy_atomic(src, lib)
        manifest["layer"]["library_path"] = lib
        out = os.path.join(layer_dir, name)
        with open(out + ".tmp", "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=4)
        os.replace(out + ".tmp", out)
        done += 1
    if not done:
        raise LayerError(f"no obs-vkcapture layer found in {ext_files}")


def remove(home: str, dest: str) -> None:
    """Removes only what install() wrote: manifests that point into dest, and dest itself."""
    layer_dir = user_layer_dir(home)
    for name in ARCHES:
        p = os.path.join(layer_dir, name)
        if _library_path(_read(p)).startswith(dest + os.sep):
            os.remove(p)
    shutil.rmtree(dest, ignore_errors=True)

"""What the machine has: a running OBS, the GPU for hardware encoding, the display size."""

import os
from typing import Optional, Tuple

DRM_DIR = "/sys/class/drm"
INTEL, AMD, NVIDIA = "0x8086", "0x1002", "0x10de"


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read().strip()
    except OSError:
        return ""


def obs_running(proc_dir: str = "/proc") -> bool:
    try:
        pids = [p for p in os.listdir(proc_dir) if p.isdigit()]
    except OSError:
        return False
    return any(_read(os.path.join(proc_dir, p, "comm")) == "obs" for p in pids)


def render_node(drm_dir: str = DRM_DIR) -> Optional[Tuple[str, str]]:
    """(/dev/dri/renderD*, PCI vendor) of the GPU to encode on: the one that drives the display (boot_vga),
    else a discrete one. With an iGPU and a dGPU, renderD128 is often the iGPU, so the node is chosen explicitly."""
    try:
        names = sorted(n for n in os.listdir(drm_dir) if n.startswith("renderD"))
    except OSError:
        return None
    nodes = []
    for n in names:
        dev = os.path.join(drm_dir, n, "device")
        nodes.append((_read(os.path.join(dev, "boot_vga")) != "1", _read(os.path.join(dev, "vendor")) == INTEL, n,
                      _read(os.path.join(dev, "vendor"))))
    if not nodes:
        return None
    best = min(nodes)
    return f"/dev/dri/{best[2]}", best[3]


def display_size(drm_dir: str = DRM_DIR) -> Optional[Tuple[int, int]]:
    """Preferred mode of the first connected display (the first line of its modes file)."""
    try:
        names = sorted(n for n in os.listdir(drm_dir) if n.startswith("card") and "-" in n)
    except OSError:
        return None
    for n in names:
        if _read(os.path.join(drm_dir, n, "status")) != "connected":
            continue
        first = _read(os.path.join(drm_dir, n, "modes")).split("\n")[0]
        w, _, h = first.partition("x")
        if w.isdigit() and h.rstrip("ip").isdigit():
            return int(w), int(h.rstrip("ip"))
    return None

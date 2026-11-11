"""Library artwork for the OBS shortcut, taken from OBS Studio's own Steam store page (app 1905180)."""

import base64
import glob
import os
import urllib.request
from typing import Dict, List

OBS_STORE_APPID = 1905180
CDN = f"https://shared.steamstatic.com/store_item_assets/steam/apps/{OBS_STORE_APPID}"
# kind -> (store file, Steam's custom artwork asset type, grid file name pattern for an appid)
KINDS = {
    "portrait": ("library_600x900_2x.jpg", 0, "{}p.*"),
    "hero": ("library_hero.jpg", 1, "{}_hero.*"),
    "logo": ("logo.png", 2, "{}_logo.*"),
    "wide": ("header.jpg", 3, "{}.[pj][np]g"),
}


def steam_roots(home: str) -> List[str]:
    roots = []
    for p in (".steam/steam", ".local/share/Steam", ".steam/debian-installation"):
        real = os.path.realpath(os.path.join(home, p))
        if os.path.isdir(os.path.join(real, "userdata")) and real not in roots:
            roots.append(real)
    return roots


def missing_kinds(home: str, appid: int) -> List[str]:
    """Kinds that no Steam account on this machine has custom artwork for, for this app."""
    grids = [g for r in steam_roots(home) for g in glob.glob(os.path.join(r, "userdata", "*", "config", "grid"))]
    return [k for k, (_, _, pattern) in KINDS.items()
            if not any(glob.glob(os.path.join(g, pattern.format(appid))) for g in grids)]


def download(kinds: List[str]) -> List[Dict]:
    out = []
    for kind in kinds:
        name, asset_type, _ = KINDS[kind]
        req = urllib.request.Request(f"{CDN}/{name}", headers={"User-Agent": "decky-obs-game-capture"})
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
        out.append({"kind": kind, "asset_type": asset_type, "ext": name.rsplit(".", 1)[1],
                    "data": base64.b64encode(data).decode()})
    return out

"""flatpak calls. Everything new goes into the user installation: no root, no password prompt."""

import os
import re
import subprocess
from typing import Dict, List, Optional

FLATHUB_URL = "https://dl.flathub.org/repo/flathub.flatpakrepo"
OBS = "com.obsproject.Studio"
VKCAPTURE_PLUGIN = "com.obsproject.Studio.Plugin.OBSVkCapture"
VKCAPTURE_LAYER = "org.freedesktop.Platform.VulkanLayer.OBSVkCapture"
FLATPAK_STEAM = "com.valvesoftware.Steam"


class FlatpakError(Exception):
    pass


def clean_env(home: str) -> dict:
    # Decky runs from a PyInstaller bundle; its LD_LIBRARY_PATH breaks system tools.
    env = dict(os.environ)
    for k in ("LD_LIBRARY_PATH", "LD_PRELOAD", "PYTHONHOME", "PYTHONPATH"):
        env.pop(k, None)
    env["PATH"] = env.get("PATH", "") + ":/usr/bin:/bin:/usr/local/bin"
    env["HOME"] = home
    env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    return env


def _run(args: List[str], env: dict, timeout: int = 60) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["flatpak", *args], env=env, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        raise FlatpakError("flatpak is not installed on this system")
    except subprocess.TimeoutExpired:
        raise FlatpakError(f"flatpak {args[0]} took longer than {timeout} s")


def available(env: dict) -> bool:
    try:
        return _run(["--version"], env).returncode == 0
    except FlatpakError:
        return False


def installed(env: dict) -> List[Dict[str, str]]:
    """Every installed app and runtime: application, branch, version, installation (user / system)."""
    r = _run(["list", "--columns=application,branch,version,installation"], env)
    if r.returncode != 0:
        return []
    rows = []
    for line in r.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 4:
            rows.append(dict(zip(("application", "branch", "version", "installation"), parts[:4])))
    return rows


def find(rows: List[Dict[str, str]], app: str) -> Optional[Dict[str, str]]:
    """The newest branch of an installed app or runtime."""
    hits = [r for r in rows if r["application"] == app]
    return max(hits, key=lambda r: branch_key(r["branch"])) if hits else None


def branch_key(branch: str):
    """'25.08' > '24.08' > 'stable': numeric branches compare by their numbers."""
    nums = re.findall(r"\d+", branch)
    return (1, tuple(int(n) for n in nums)) if nums else (0, ())


def ensure_flathub(env: dict) -> None:
    r = _run(["remote-add", "--user", "--if-not-exists", "flathub", FLATHUB_URL], env, timeout=120)
    if r.returncode != 0:
        raise FlatpakError(f"could not add Flathub: {r.stderr.strip()}")


def remote_branches(app: str, env: dict) -> List[str]:
    r = _run(["remote-ls", "--user", "flathub", "--columns=application,branch"], env, timeout=300)
    if r.returncode != 0:
        raise FlatpakError(f"could not read Flathub: {r.stderr.strip()}")
    out = {line.split("\t")[1] for line in r.stdout.splitlines() if line.split("\t")[0] == app and "\t" in line}
    return sorted(out, key=branch_key)


def runtime_branch(app: str, env: dict) -> Optional[str]:
    """Branch of the org.freedesktop.Platform an installed app runs on (flatpak Steam's games need a layer of that branch)."""
    r = _run(["info", "--show-runtime", app], env)
    if r.returncode != 0:
        return None
    parts = r.stdout.strip().split("/")
    return parts[-1] if len(parts) == 3 else None


def install(refs: List[str], env: dict) -> None:
    """Installs, or updates when already there."""
    r = _run(["install", "--user", "--noninteractive", "--or-update", "-y", "flathub", *refs], env, timeout=1800)
    if r.returncode != 0:
        msg = r.stderr.strip() or r.stdout.strip() or f"exit code {r.returncode}"
        raise FlatpakError(f"flatpak install failed: {msg.splitlines()[-1]}")


def location(ref: str, env: dict) -> Optional[str]:
    r = _run(["info", "--show-location", ref], env)
    return r.stdout.strip() or None if r.returncode == 0 else None

"""A silent virtual microphone in PipeWire, for machines with no microphone connected.

Without one, WirePlumber makes the monitor of an output the default source, Steam finds no active input device and
its Settings → Audio page fails to render. The virtual source has a session priority above every output (their
monitors are the fallback candidates) and below real microphones, so a connected microphone still becomes the default.

It lives in two places: a PipeWire drop-in that creates it at every PipeWire start, and a node created right away
with pw-cli (object.linger keeps it after pw-cli exits), so the toggle works without restarting PipeWire.
"""

import json
import os
import subprocess
from typing import List, Optional

NODE_NAME = "virtual-microphone"
DESCRIPTION = "Virtual Microphone"
# Outputs get ~600-1000 from WirePlumber, ALSA / USB / Bluetooth microphones ~2000 and more.
PRIORITY = 1500
CONF_NAME = "90-obs-game-capture-virtual-mic.conf"

PROPS = {
    "factory.name": "support.null-audio-sink",
    "node.name": NODE_NAME,
    "node.description": DESCRIPTION,
    "media.class": "Audio/Source/Virtual",
    "audio.position": ["FL", "FR"],
    "priority.session": PRIORITY,
    "priority.driver": PRIORITY,
}


class VirtualMicError(Exception):
    pass


def conf_path(home: str) -> str:
    return os.path.join(home, ".config", "pipewire", "pipewire.conf.d", CONF_NAME)


def _spa(value) -> str:
    """SPA JSON (what PipeWire configs and pw-cli take): JSON with arrays/objects written the same way."""
    if isinstance(value, dict):
        return "{ " + " ".join(f"{k} = {_spa(v)}" for k, v in value.items()) + " }"
    if isinstance(value, list):
        return "[ " + " ".join(_spa(v) for v in value) + " ]"
    return json.dumps(value)


def conf_text() -> str:
    return (
        "# Written by the OBS Game Capture Decky plugin (Virtual microphone toggle); the toggle removes it.\n"
        "context.objects = [\n"
        f"  {{ factory = adapter args = {_spa(PROPS)} }}\n"
        "]\n"
    )


def configured(home: str) -> bool:
    return os.path.isfile(conf_path(home))


def _run(args: List[str], env: dict) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(args, env=env, capture_output=True, text=True, timeout=15)
    except FileNotFoundError:
        raise VirtualMicError(f"{args[0]} is not installed: is PipeWire running on this system?")
    except subprocess.TimeoutExpired:
        raise VirtualMicError(f"{args[0]} did not answer")


def node_ids(dump: list) -> List[int]:
    """Ids of the plugin's nodes in pw-dump output."""
    return [o["id"] for o in dump if o.get("type") == "PipeWire:Interface:Node"
            and ((o.get("info") or {}).get("props") or {}).get("node.name") == NODE_NAME]


def _live_ids(env: dict) -> List[int]:
    r = _run(["pw-dump"], env)
    if r.returncode != 0:
        raise VirtualMicError(f"pw-dump failed: {r.stderr.strip() or r.returncode}")
    try:
        return node_ids(json.loads(r.stdout or "[]"))
    except ValueError:
        raise VirtualMicError("pw-dump returned something that is not JSON")


def running(env: dict) -> Optional[bool]:
    """The node exists now; None when PipeWire cannot be asked."""
    try:
        return bool(_live_ids(env))
    except VirtualMicError:
        return None


def enable(home: str, env: dict) -> None:
    path = conf_path(home)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        f.write(conf_text())
    os.replace(path + ".tmp", path)
    if _live_ids(env):
        return
    r = _run(["pw-cli", "create-node", "adapter", _spa({**PROPS, "object.linger": True})], env)
    if r.returncode != 0 or "rror" in r.stdout:
        raise VirtualMicError(f"pw-cli could not create the microphone: {(r.stderr or r.stdout).strip()}")


def disable(home: str, env: dict) -> None:
    try:
        os.remove(conf_path(home))
    except FileNotFoundError:
        pass
    for node in _live_ids(env):
        _run(["pw-cli", "destroy", str(node)], env)

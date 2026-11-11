"""OBS Studio (flatpak) settings for streaming games: hardware encoding, 1080p60, a Game Capture source.

Only the keys listed here are changed; everything else in the user's profile and scene collection stays.
The first time a file is changed its original is kept next to it as *.obs-game-capture.bak.
OBS rewrites its files on exit, so this must run while OBS is closed.
"""

import configparser
import json
import os
import shutil
import uuid
from typing import Optional, Tuple

from .system import AMD, INTEL

CONFIG_REL = os.path.join(".var", "app", "com.obsproject.Studio", "config", "obs-studio")
BACKUP_SUFFIX = ".obs-game-capture.bak"
SOURCE_ID = "vkcapture-source"
SOURCE_NAME = "Game Capture"
STREAM_BITRATE = 6000  # kbps, Twitch's recommended maximum
AUDIO_BITRATE = 160
FPS = 60
MAX_OUTPUT_HEIGHT = 1080
DEFAULT_NAME = "Untitled"  # what OBS itself calls the first profile and scene collection
OBS_BOUNDS_SCALE_INNER = 2
OBS_ALIGN_TOP_LEFT = 5


def config_dir(home: str) -> str:
    return os.path.join(home, CONFIG_REL)


def _ini(path: str) -> configparser.ConfigParser:
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    cp.optionxform = str  # OBS keys are case sensitive
    if os.path.isfile(path):
        cp.read(path, encoding="utf-8-sig")
    return cp


def _backup(path: str) -> None:
    if os.path.isfile(path) and not os.path.exists(path + BACKUP_SUFFIX):
        shutil.copy2(path, path + BACKUP_SUFFIX)


def _write_ini(cp: configparser.ConfigParser, path: str) -> None:
    _backup(path)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        cp.write(f, space_around_delimiters=False)
    os.replace(path + ".tmp", path)


def _read_json(path: str) -> Optional[dict]:
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _write_json(path: str, data: dict) -> None:
    _backup(path)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
    os.replace(path + ".tmp", path)


def _set(cp: configparser.ConfigParser, section: str, key: str, value) -> None:
    if not cp.has_section(section):
        cp.add_section(section)
    cp.set(section, key, str(value).lower() if isinstance(value, bool) else str(value))


def output_size(canvas: Tuple[int, int]) -> Tuple[int, int]:
    """The stream resolution: the canvas scaled down to at most 1080 lines, even width."""
    w, h = canvas
    if h <= MAX_OUTPUT_HEIGHT:
        return w, h
    return round(w * MAX_OUTPUT_HEIGHT / h / 2) * 2, MAX_OUTPUT_HEIGHT


def encoder_for(gpu: Optional[Tuple[str, str]]) -> Tuple[str, dict]:
    """VA-API on AMD and Intel, x264 elsewhere (VA-API does not exist on NVIDIA's driver)."""
    common = {"rate_control": "CBR", "bitrate": STREAM_BITRATE, "keyint_sec": 2}
    if gpu and gpu[1] in (AMD, INTEL):
        return "ffmpeg_vaapi_tex", {**common, "vaapi_device": gpu[0], "profile": 100}  # 100 = H.264 High
    return "obs_x264", {**common, "preset": "veryfast"}


def _names(root: str) -> Tuple[configparser.ConfigParser, str, str, str, str]:
    """user.ini (global.ini before OBS 31) and the current profile and scene collection."""
    user_ini = os.path.join(root, "user.ini")
    u = _ini(user_ini)
    src = u if u.has_section("Basic") else _ini(os.path.join(root, "global.ini"))
    get = lambda key, default: src.get("Basic", key, fallback="") or default  # noqa: E731
    profile = get("Profile", DEFAULT_NAME)
    profile_dir = get("ProfileDir", profile)
    collection = get("SceneCollection", DEFAULT_NAME)
    collection_file = get("SceneCollectionFile", collection)
    if not collection_file.endswith(".json"):
        collection_file += ".json"
    return u, profile, profile_dir, collection, collection_file


def _audio_device(name: str, kind: str) -> dict:
    return {"name": name, "uuid": str(uuid.uuid4()), "id": kind, "versioned_id": kind,
            "settings": {"device_id": "default"}, "mixers": 255, "enabled": True, "volume": 1.0, "muted": False}


def new_collection(name: str) -> dict:
    return {
        "name": name, "current_scene": "Scene", "current_program_scene": "Scene", "scene_order": [{"name": "Scene"}],
        "sources": [], "groups": [], "transitions": [], "current_transition": "Fade", "transition_duration": 300,
        "quick_transitions": [], "saved_projectors": [], "preview_locked": False, "modules": {},
        "DesktopAudioDevice1": _audio_device("Desktop Audio", "pulse_output_capture"),
        "AuxAudioDevice1": _audio_device("Mic/Aux", "pulse_input_capture"),
    }


def add_game_capture(data: dict, canvas: Tuple[int, int]) -> bool:
    """Adds a Game Capture source on top of the current scene, scaled to fill the canvas. False if there is one."""
    sources = data.setdefault("sources", [])
    if any(s.get("id") == SOURCE_ID for s in sources):
        return False
    scenes = [s for s in sources if s.get("id") == "scene"]
    if not scenes:
        scene = {"name": "Scene", "uuid": str(uuid.uuid4()), "id": "scene", "versioned_id": "scene",
                 "settings": {"id_counter": 0, "custom_size": False, "items": []}, "enabled": True}
        sources.append(scene)
        scenes = [scene]
        data.update(current_scene="Scene", current_program_scene="Scene", scene_order=[{"name": "Scene"}])
    target = next((s for s in scenes if s.get("name") == data.get("current_scene")), scenes[0])
    src = {"name": SOURCE_NAME, "uuid": str(uuid.uuid4()), "id": SOURCE_ID, "versioned_id": SOURCE_ID,
           "settings": {}, "enabled": True, "mixers": 0}
    sources.insert(0, src)
    settings = target.setdefault("settings", {})
    items = settings.setdefault("items", [])
    item_id = max([settings.get("id_counter", 0)] + [i.get("id", 0) for i in items]) + 1
    settings["id_counter"] = item_id
    items.append({  # last item = top of the scene
        "name": SOURCE_NAME, "source_uuid": src["uuid"], "visible": True, "locked": False, "rot": 0.0,
        "pos": {"x": 0.0, "y": 0.0}, "scale": {"x": 1.0, "y": 1.0}, "align": OBS_ALIGN_TOP_LEFT,
        "bounds_type": OBS_BOUNDS_SCALE_INNER, "bounds_align": 0, "bounds": {"x": float(canvas[0]), "y": float(canvas[1])},
        "crop_left": 0, "crop_top": 0, "crop_right": 0, "crop_bottom": 0, "id": item_id,
    })
    return True


def configure(home: str, canvas: Tuple[int, int], gpu: Optional[Tuple[str, str]]) -> dict:
    root = config_dir(home)
    os.makedirs(os.path.join(root, "basic", "scenes"), exist_ok=True)
    u, profile, profile_dir, collection, collection_file = _names(root)

    # OBS that was never started: name the profile and collection, and skip its first-run wizard
    if not u.has_section("Basic"):
        for key, value in (("Profile", profile), ("ProfileDir", profile_dir), ("SceneCollection", collection),
                           ("SceneCollectionFile", collection_file)):
            _set(u, "Basic", key, value)
        if not u.get("General", "FirstRun", fallback=""):
            _set(u, "General", "FirstRun", True)
        _write_ini(u, os.path.join(root, "user.ini"))

    pdir = os.path.join(root, "basic", "profiles", profile_dir)
    os.makedirs(pdir, exist_ok=True)
    basic_path = os.path.join(pdir, "basic.ini")
    basic = _ini(basic_path)
    if not basic.get("General", "Name", fallback=""):
        _set(basic, "General", "Name", profile)
    encoder, encoder_settings = encoder_for(gpu)
    out = output_size(canvas)
    for section, key, value in (
        ("Output", "Mode", "Advanced"),  # VA-API is offered only in Advanced output mode
        ("AdvOut", "Encoder", encoder), ("AdvOut", "ApplyServiceSettings", True), ("AdvOut", "UseRescale", False),
        ("AdvOut", "TrackIndex", 1), ("AdvOut", "Track1Bitrate", AUDIO_BITRATE),
        ("Video", "BaseCX", canvas[0]), ("Video", "BaseCY", canvas[1]),
        ("Video", "OutputCX", out[0]), ("Video", "OutputCY", out[1]),
        ("Video", "FPSType", 0), ("Video", "FPSCommon", FPS),
    ):
        _set(basic, section, key, value)
    _write_ini(basic, basic_path)

    enc_path = os.path.join(pdir, "streamEncoder.json")
    enc = _read_json(enc_path) or {}
    enc.update(encoder_settings)
    _write_json(enc_path, enc)

    service_path = os.path.join(pdir, "service.json")
    if not os.path.isfile(service_path):  # never touch a configured service: it holds the stream key
        _write_json(service_path, {"type": "rtmp_common",
                                   "settings": {"service": "Twitch", "server": "auto", "protocol": "RTMP"}})

    scene_path = os.path.join(root, "basic", "scenes", collection_file)
    data = _read_json(scene_path) or new_collection(collection)
    added = add_game_capture(data, canvas)
    if added or not os.path.isfile(scene_path):
        _write_json(scene_path, data)

    return {"profile": profile, "collection": collection, "encoder": encoder,
            "canvas": f"{canvas[0]}x{canvas[1]}", "output": f"{out[0]}x{out[1]}", "fps": FPS,
            "bitrate": STREAM_BITRATE, "added_source": added}


def configured(home: str) -> bool:
    """The current scene collection has a Game Capture source."""
    root = config_dir(home)
    if not os.path.isdir(root):
        return False
    data = _read_json(os.path.join(root, "basic", "scenes", _names(root)[4])) or {}
    return any(s.get("id") == SOURCE_ID for s in data.get("sources", []))

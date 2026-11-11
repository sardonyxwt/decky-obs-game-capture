"""Offline tests for the backend: python3 tests/test_backend.py  (or python3 -m pytest tests/)"""

import configparser
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "py_modules"))

from obscapture import artwork, flatpak, layer, obsconfig, system  # noqa: E402


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def fake_extension(root):
    files = os.path.join(root, "files")
    for name, arch in layer.ARCHES.items():
        write(os.path.join(files, "lib", arch, layer.LIBRARY), "ELF")
        write(os.path.join(files, "share", "vulkan", "implicit_layer.d", name), json.dumps({
            "file_format_version": "1.1.2",
            "layer": {"name": "VK_LAYER_OBS_vkcapture", "library_path": f"/usr/lib/extensions/vulkan/OBSVkCapture/lib/{arch}/{layer.LIBRARY}",
                      "enable_environment": {"OBS_VKCAPTURE": "1"}}}))
    return files


def test_layer_install_and_remove():
    with tempfile.TemporaryDirectory() as tmp:
        home, dest = os.path.join(tmp, "home"), os.path.join(tmp, "data", "vkcapture")
        os.environ.pop("XDG_DATA_HOME", None)
        files = fake_extension(os.path.join(tmp, "ext"))
        none = (os.path.join(tmp, "nosys"),)
        assert layer.status(home, dest, none) is None
        layer.install(files, home, dest)
        assert layer.status(home, dest, none) == "plugin"
        m = json.load(open(os.path.join(home, ".local/share/vulkan/implicit_layer.d/obs_vkcapture_64.json")))
        assert m["layer"]["library_path"] == os.path.join(dest, "x86_64-linux-gnu", layer.LIBRARY)
        assert m["layer"]["enable_environment"] == {"OBS_VKCAPTURE": "1"}  # stays opt-in per game
        # a manifest the plugin did not write is left alone
        other = os.path.join(home, ".local/share/vulkan/implicit_layer.d/obs_vkcapture_32.json")
        write(other, json.dumps({"layer": {"library_path": "/usr/lib/other.so"}}))
        layer.remove(home, dest)
        assert not os.path.exists(os.path.join(home, ".local/share/vulkan/implicit_layer.d/obs_vkcapture_64.json"))
        assert os.path.exists(other)
        assert not os.path.exists(dest)
        # a system package wins
        sysdir = os.path.join(tmp, "sys")
        write(os.path.join(sysdir, "obs_vkcapture_64.json"), "{}")
        assert layer.status(home, dest, (sysdir,)) == "system"


def test_render_node_and_display():
    with tempfile.TemporaryDirectory() as drm:
        write(os.path.join(drm, "renderD128/device/vendor"), "0x8086")
        write(os.path.join(drm, "renderD128/device/boot_vga"), "0")
        write(os.path.join(drm, "renderD129/device/vendor"), "0x1002")
        write(os.path.join(drm, "renderD129/device/boot_vga"), "1")
        assert system.render_node(drm) == ("/dev/dri/renderD129", "0x1002")
        write(os.path.join(drm, "card1-DP-1/status"), "disconnected")
        write(os.path.join(drm, "card2-HDMI-A-3/status"), "connected")
        write(os.path.join(drm, "card2-HDMI-A-3/modes"), "2560x1440\n1920x1080\n")
        assert system.display_size(drm) == (2560, 1440)


def test_obs_running():
    with tempfile.TemporaryDirectory() as proc:
        write(os.path.join(proc, "10/comm"), "steam")
        assert not system.obs_running(proc)
        write(os.path.join(proc, "11/comm"), "obs")
        assert system.obs_running(proc)


def test_output_size_and_encoder():
    assert obsconfig.output_size((2560, 1440)) == (1920, 1080)
    assert obsconfig.output_size((3440, 1440)) == (2580, 1080)
    assert obsconfig.output_size((1280, 800)) == (1280, 800)
    enc, s = obsconfig.encoder_for(("/dev/dri/renderD129", "0x1002"))
    assert enc == "ffmpeg_vaapi_tex" and s["vaapi_device"] == "/dev/dri/renderD129"
    assert obsconfig.encoder_for(("/dev/dri/renderD128", "0x10de"))[0] == "obs_x264"
    assert obsconfig.encoder_for(None)[0] == "obs_x264"


def existing_obs(home):
    root = obsconfig.config_dir(home)
    write(os.path.join(root, "user.ini"),
          "[General]\nFirstRun=true\n\n[Basic]\nProfile=Main\nProfileDir=Main\nSceneCollection=Mine\nSceneCollectionFile=Mine\n")
    write(os.path.join(root, "basic/profiles/Main/basic.ini"),
          "[General]\nName=Main\n\n[Output]\nMode=Simple\n\n[SimpleOutput]\nVBitrate=2500\n")
    write(os.path.join(root, "basic/profiles/Main/service.json"),
          json.dumps({"type": "rtmp_common", "settings": {"service": "Twitch", "key": "secret"}}))
    write(os.path.join(root, "basic/scenes/Mine.json"), json.dumps({
        "name": "Mine", "current_scene": "Scene",
        "sources": [{"name": "Screen", "uuid": "u1", "id": "pipewire-screen-capture-source", "settings": {}},
                    {"name": "Scene", "uuid": "u2", "id": "scene",
                     "settings": {"id_counter": 3, "items": [{"name": "Screen", "source_uuid": "u1", "id": 2}]}}]}))
    return root


def test_configure_existing_profile():
    with tempfile.TemporaryDirectory() as home:
        root = existing_obs(home)
        r = obsconfig.configure(home, (2560, 1440), ("/dev/dri/renderD129", "0x1002"))
        assert r["profile"] == "Main" and r["collection"] == "Mine" and r["added_source"]
        assert r["output"] == "1920x1080" and r["encoder"] == "ffmpeg_vaapi_tex"
        ini = configparser.ConfigParser(interpolation=None)
        ini.optionxform = str
        ini.read(os.path.join(root, "basic/profiles/Main/basic.ini"))
        assert ini["Output"]["Mode"] == "Advanced"
        assert ini["SimpleOutput"]["VBitrate"] == "2500"  # untouched keys stay
        assert ini["Video"]["OutputCX"] == "1920" and ini["Video"]["FPSCommon"] == "60"
        assert ini["AdvOut"]["ApplyServiceSettings"] == "true"
        text = open(os.path.join(root, "basic/profiles/Main/basic.ini")).read()
        assert "Mode=Advanced" in text  # OBS format: no spaces around '='
        enc = json.load(open(os.path.join(root, "basic/profiles/Main/streamEncoder.json")))
        assert enc["bitrate"] == 6000 and enc["rate_control"] == "CBR" and enc["keyint_sec"] == 2
        service = json.load(open(os.path.join(root, "basic/profiles/Main/service.json")))
        assert service["settings"]["key"] == "secret"
        scene = json.load(open(os.path.join(root, "basic/scenes/Mine.json")))
        caps = [s for s in scene["sources"] if s["id"] == obsconfig.SOURCE_ID]
        assert len(caps) == 1
        items = next(s for s in scene["sources"] if s["id"] == "scene")["settings"]["items"]
        assert items[-1]["source_uuid"] == caps[0]["uuid"] and items[-1]["id"] == 4
        assert items[-1]["bounds"] == {"x": 2560.0, "y": 1440.0}
        assert os.path.exists(os.path.join(root, "basic/scenes/Mine.json" + obsconfig.BACKUP_SUFFIX))
        assert obsconfig.configured(home)
        # running it again changes nothing in the scene and keeps the first backup
        backup = open(os.path.join(root, "basic/profiles/Main/basic.ini" + obsconfig.BACKUP_SUFFIX)).read()
        assert "Mode=Simple" in backup
        r2 = obsconfig.configure(home, (2560, 1440), None)
        assert not r2["added_source"] and r2["encoder"] == "obs_x264"
        assert "Mode=Simple" in open(os.path.join(root, "basic/profiles/Main/basic.ini" + obsconfig.BACKUP_SUFFIX)).read()


def test_configure_fresh_obs():
    with tempfile.TemporaryDirectory() as home:
        assert not obsconfig.configured(home)
        r = obsconfig.configure(home, (1920, 1080), None)
        root = obsconfig.config_dir(home)
        assert r["profile"] == "Untitled" and r["output"] == "1920x1080"
        u = open(os.path.join(root, "user.ini")).read()
        assert "SceneCollectionFile=Untitled.json" in u and "FirstRun=true" in u
        service = json.load(open(os.path.join(root, "basic/profiles/Untitled/service.json")))
        assert service["settings"]["service"] == "Twitch"
        scene = json.load(open(os.path.join(root, "basic/scenes/Untitled.json")))
        assert scene["DesktopAudioDevice1"]["id"] == "pulse_output_capture"
        assert obsconfig.configured(home)


def test_flatpak_helpers():
    assert flatpak.branch_key("25.08") > flatpak.branch_key("24.08") > flatpak.branch_key("stable")
    rows = [{"application": "x", "branch": "24.08", "version": "1", "installation": "user"},
            {"application": "x", "branch": "25.08", "version": "1", "installation": "user"}]
    assert flatpak.find(rows, "x")["branch"] == "25.08"
    assert flatpak.find(rows, "y") is None


def test_artwork_missing_kinds():
    with tempfile.TemporaryDirectory() as home:
        grid = os.path.join(home, ".local/share/Steam/userdata/1/config/grid")
        write(os.path.join(grid, "123p.png"), "x")
        write(os.path.join(grid, "123.json"), "{}")  # logo position, not the wide capsule
        assert artwork.missing_kinds(home, 123) == ["hero", "logo", "wide"]
        write(os.path.join(grid, "123.jpg"), "x")
        assert artwork.missing_kinds(home, 123) == ["hero", "logo"]


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in tests:
        fn()
        print("ok", fn.__name__)
    print(f"{len(tests)} passed")

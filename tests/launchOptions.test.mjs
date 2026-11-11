// node tests/launchOptions.test.mjs <dir with compiled launchOptions.js>  (see CLAUDE.md)
import assert from "node:assert/strict";
import path from "node:path";
import { pathToFileURL } from "node:url";

const dir = process.argv[2];
const { addCaptureFlag, removeCaptureFlag, hasCaptureFlag } = await import(pathToFileURL(path.join(dir, "launchOptions.js")));

const cases = [
  ["", "OBS_VKCAPTURE=1 %command%"],
  ["%command%", "OBS_VKCAPTURE=1 %command%"],
  ["-dx11 -nolauncher", "OBS_VKCAPTURE=1 %command% -dx11 -nolauncher"],
  ["PROTON_LOG=1 %command% -dx11", "OBS_VKCAPTURE=1 PROTON_LOG=1 %command% -dx11"],
  ['"/home/u/homebrew/data/depth3d-glasses/bin/depth3d-run" 42 %command%',
    'OBS_VKCAPTURE=1 "/home/u/homebrew/data/depth3d-glasses/bin/depth3d-run" 42 %command%'],
  ["gamemoderun  %command%", "OBS_VKCAPTURE=1 gamemoderun %command%"],
  ["run com.obsproject.Studio", "OBS_VKCAPTURE=1 %command% run com.obsproject.Studio"],
];
for (const [input, want] of cases) {
  const added = addCaptureFlag(input);
  assert.equal(added, want, `add: ${input}`);
  assert.equal(addCaptureFlag(added), added, `add twice: ${input}`);
  assert.ok(hasCaptureFlag(added));
  const back = removeCaptureFlag(added);
  assert.equal(back, input.replace(/\s+/g, " ").trim() === "%command%" ? "" : input.replace(/\s+/g, " ").trim(), `remove: ${input}`);
}
assert.ok(!hasCaptureFlag("MY_OBS_VKCAPTURE=1 %command%"));
assert.ok(!hasCaptureFlag("OBS_VKCAPTURE=10 %command%"));
assert.equal(removeCaptureFlag("MY_OBS_VKCAPTURE=1 %command%"), "MY_OBS_VKCAPTURE=1 %command%");
console.log(`${cases.length} launch option cases passed`);

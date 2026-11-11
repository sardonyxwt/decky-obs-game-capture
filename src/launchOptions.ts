// Pure helpers for Steam launch options. No Steam globals here, so they can be unit tested.
//
// The flag goes at the very start: an environment assignment only works in front of the command,
// and other tools' wrappers ("gamemoderun %command%", Depth3D's "<wrapper> <appid> %command%")
// are commands themselves.

export const CAPTURE_FLAG = "OBS_VKCAPTURE=1";
const COMMAND = "%command%";
const FLAG_RE = /(^|\s)OBS_VKCAPTURE=1(?=\s|$)/g;

function tidy(s: string): string {
  return s.replace(/\s+/g, " ").trim();
}

export function hasCaptureFlag(current: string): boolean {
  return new RegExp(FLAG_RE.source).test(current || "");
}

/** Adds the flag to existing launch options. */
export function addCaptureFlag(current: string): string {
  const cur = tidy(current || "");
  if (hasCaptureFlag(cur)) return cur;
  if (!cur) return `${CAPTURE_FLAG} ${COMMAND}`;
  if (cur.includes(COMMAND)) return `${CAPTURE_FLAG} ${cur}`;
  // Only game arguments, e.g. "-dx11 -nolauncher"
  return `${CAPTURE_FLAG} ${COMMAND} ${cur}`;
}

/** Removes the flag; a leading "%command%" that is left over goes too (bare arguments mean the same to Steam). */
export function removeCaptureFlag(current: string): string {
  const cur = tidy((current || "").replace(FLAG_RE, " "));
  if (cur === COMMAND) return "";
  return cur.startsWith(`${COMMAND} `) ? cur.slice(COMMAND.length + 1) : cur;
}

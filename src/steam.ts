// Thin, defensive wrappers around Steam client globals available to Decky plugins.
import { Artwork } from "./backend";
import { addCaptureFlag, hasCaptureFlag, removeCaptureFlag } from "./launchOptions";

declare const SteamClient: any;
declare const appStore: any;

const APP_TYPE_GAME = 1;
const APP_TYPE_SHORTCUT = 1073741824;
export const OBS_NAME = "OBS Studio";
const FLATPAK = "/usr/bin/flatpak";
const OBS_ARGS = "run com.obsproject.Studio";

interface Details {
  strLaunchOptions?: string;
  strShortcutExe?: string;
}

/**
 * App details, always asked from Steam: appDetailsStore keeps stale launch options for apps
 * whose page is not open (seen on hardware: a flag set a minute earlier was missing there),
 * and writing back from a stale copy would drop the user's own options.
 */
async function details(appid: number): Promise<Details | null> {
  if (!SteamClient?.Apps?.RegisterForAppDetails) return null;
  return new Promise((resolve) => {
    let reg: any = null;
    const done = (v: Details | null) => {
      clearTimeout(timer);
      try {
        reg?.unregister?.();
      } catch (_) {
        /* ignore */
      }
      resolve(v);
    };
    const timer = setTimeout(() => done(null), 3000);
    try {
      reg = SteamClient.Apps.RegisterForAppDetails(appid, (d: any) => {
        if (d && typeof d.strLaunchOptions === "string") done(d);
      });
    } catch (_) {
      done(null);
    }
  });
}

/** The OBS shortcut: a non-Steam app that runs the OBS flatpak. */
export async function findObsShortcut(): Promise<number | null> {
  const shortcuts: any[] = (appStore?.allApps ?? []).filter((a: any) => a.app_type === APP_TYPE_SHORTCUT);
  for (const a of shortcuts.filter((s) => /obs/i.test(s.display_name ?? ""))) {
    const d = await details(a.appid);
    if (d?.strLaunchOptions?.includes("com.obsproject.Studio") || a.display_name === OBS_NAME) return a.appid;
  }
  return null;
}

/** Installed Steam games and every non-Steam shortcut, except OBS itself. */
export function targetApps(obsAppid: number | null): number[] {
  return (appStore?.allApps ?? [])
    .filter((a: any) => (a.app_type === APP_TYPE_GAME && a.installed) || a.app_type === APP_TYPE_SHORTCUT)
    .map((a: any) => a.appid as number)
    .filter((id: number) => id !== obsAppid);
}

/** Adds the flag to one app. true = added now, false = it was there already, null = unreadable (next sweep). */
export async function addFlag(appid: number): Promise<boolean | null> {
  const d = await details(appid);
  if (!d || typeof d.strLaunchOptions !== "string") return null;
  if (hasCaptureFlag(d.strLaunchOptions)) return false;
  SteamClient.Apps.SetAppLaunchOptions(appid, addCaptureFlag(d.strLaunchOptions));
  return true;
}

export async function removeFlag(appid: number): Promise<boolean> {
  const d = await details(appid);
  if (!d || typeof d.strLaunchOptions !== "string") return false;
  if (hasCaptureFlag(d.strLaunchOptions)) SteamClient.Apps.SetAppLaunchOptions(appid, removeCaptureFlag(d.strLaunchOptions));
  return true;
}

/** Runs fn over items a few at a time (each call may wait for Steam to load app details). */
export async function forEachLimited<T>(items: T[], fn: (item: T) => Promise<void>, limit = 6): Promise<void> {
  let next = 0;
  const worker = async () => {
    while (next < items.length) await fn(items[next++]);
  };
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker));
}

/** Adds the OBS shortcut (native, no Proton) unless there is one; returns its appid. */
export async function ensureObsShortcut(home: string): Promise<{ appid: number; created: boolean }> {
  const existing = await findObsShortcut();
  if (existing) return { appid: existing, created: false };
  // AddShortcut quotes the exe itself and mangles a quoted start dir, so both are set again
  // afterwards in the "quoted" form every other shortcut has.
  const id: number = await SteamClient.Apps.AddShortcut(OBS_NAME, FLATPAK, home, OBS_ARGS);
  SteamClient.Apps.SetShortcutName(id, OBS_NAME);
  SteamClient.Apps.SetShortcutExe(id, `"${FLATPAK}"`);
  SteamClient.Apps.SetShortcutStartDir(id, `"${home}"`);
  SteamClient.Apps.SetAppLaunchOptions(id, OBS_ARGS);
  SteamClient.Apps.SpecifyCompatTool(id, "");
  return { appid: id >>> 0, created: true };
}

export function setShortcutIcon(appid: number, path: string) {
  if (path) SteamClient.Apps.SetShortcutIcon(appid, path);
}

export async function setArtwork(appid: number, images: Artwork[]) {
  for (const img of images) {
    await SteamClient.Apps.SetCustomArtworkForApp(appid, img.data, img.ext, img.asset_type);
  }
}

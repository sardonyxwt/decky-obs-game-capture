import { callable } from "@decky/api";

export interface FlatpakRef {
  application: string;
  branch: string;
  version: string;
  installation: "user" | "system" | string;
}

export type SetupStep = "flathub" | "obs" | "vkcapture" | "layer" | "obs_config";

export interface ObsConfigResult {
  profile: string;
  collection: string;
  encoder: string;
  canvas: string;
  output: string;
  fps: number;
  bitrate: number;
  added_source: boolean;
}

export interface SetupState {
  running: boolean;
  step: SetupStep | "";
  done: SetupStep[];
  errors: Partial<Record<SetupStep, string>>;
  obs_config: ObsConfigResult | null;
}

export type State =
  | {
      ok: true;
      flatpak: boolean;
      obs: FlatpakRef | null;
      vkcapture: FlatpakRef | null;
      layer: "plugin" | "system" | null;
      obs_configured: boolean;
      obs_running: boolean;
      virtual_mic_running: boolean | null;
      icon: string;
      home: string;
      enabled: boolean;
      applied: number[];
      virtual_mic: boolean;
      setup: SetupState;
    }
  | { ok: false; error: string };

export interface Artwork {
  kind: string;
  asset_type: number;
  ext: string;
  data: string;
}

export const getState = callable<[], State>("get_state");
export const startSetup = callable<[], { ok: boolean }>("start_setup");
export const saveGames = callable<[enabled: boolean, applied: number[]], { ok: boolean }>("save_games");
export const setVirtualMic = callable<[enabled: boolean], { ok: true } | { ok: false; error: string }>(
  "set_virtual_mic",
);
export const getArtwork = callable<[appid: number], { ok: true; images: Artwork[] } | { ok: false; error: string }>(
  "get_artwork",
);

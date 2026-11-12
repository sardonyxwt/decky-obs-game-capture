import { ButtonItem, Field, PanelSection, PanelSectionRow, staticClasses, ToggleField } from "@decky/ui";
import { addEventListener, definePlugin, removeEventListener, toaster } from "@decky/api";
import { useEffect, useState } from "react";
import { FaVideo } from "react-icons/fa";
import { getArtwork, getState, saveGames, SetupState, SetupStep, setVirtualMic, startSetup, State } from "./backend";
import { t, tr } from "./i18n";
import {
  addFlag, ensureObsShortcut, findObsShortcut, forEachLimited, removeFlag, setArtwork, setShortcutIcon, targetApps,
} from "./steam";

type Ready = Extract<State, { ok: true }>;

// New games get the flag within this time, and a flag something else took out comes back
// (Steam has no "game installed" event for plugins).
const SWEEP_EVERY_MS = 60 * 1000;

const STEP_TEXT: Record<SetupStep | "steam", [string, string]> = {
  flathub: ["Flathub repository", "Репозиторий Flathub"],
  obs: ["OBS Studio", "OBS Studio"],
  vkcapture: ["OBS game capture plugin (obs-vkcapture)", "Плагин захвата игр для OBS (obs-vkcapture)"],
  layer: ["Vulkan capture layer for games", "Слой захвата Vulkan для игр"],
  obs_config: ["OBS settings for streaming", "Настройки OBS для стрима"],
  steam: ["OBS in the Steam library", "OBS в библиотеке Steam"],
};

// ---------------- shared state ----------------
let current: Ready | null = null;
let obsAppid: number | null = null;
let busy: "" | "setup" | "games" | "mic" = "";
const listeners = new Set<() => void>();
const notify = () => listeners.forEach((l) => l());

async function refresh(): Promise<Ready | null> {
  const s = await getState();
  if (!s.ok) {
    toaster.toast({ title: "OBS Game Capture", body: s.error });
    return current;
  }
  current = s;
  obsAppid = await findObsShortcut();
  notify();
  return s;
}

// ---------------- launch options of games ----------------
let syncing: Promise<void> | null = null;

/** Enabled: every game without the flag gets it. Disabled: it is taken out where the plugin put it. */
function syncGames(enable: boolean): Promise<void> {
  const run = async () => {
    const s = await refresh(); // the backend's record is the truth, not the panel's copy
    if (!s) return;
    const applied = new Set(s.applied);
    let changed = enable !== s.enabled;
    if (enable) {
      await forEachLimited(targetApps(obsAppid), async (id) => {
        if ((await addFlag(id)) === true && !applied.has(id)) {
          applied.add(id);
          changed = true;
        }
      });
    } else {
      await forEachLimited([...applied], async (id) => {
        if (await removeFlag(id)) applied.delete(id);
      });
      changed = true;
    }
    if (!changed) return;
    await saveGames(enable, [...applied]);
    await refresh();
  };
  // one pass at a time; a toggle while a sweep runs waits for it
  syncing = (syncing ?? Promise.resolve()).then(run).catch(() => undefined).finally(() => {
    syncing = null;
  });
  return syncing;
}

// ---------------- setup ----------------
async function finishSetup(setup: SetupState) {
  const s = await refresh();
  const failed = Object.keys(setup.errors).length;
  if (s?.obs) {
    try {
      const { appid, created } = await ensureObsShortcut(s.home);
      obsAppid = appid;
      if (created) setShortcutIcon(appid, s.icon);
      const art = await getArtwork(appid);
      if (art.ok) await setArtwork(appid, art.images);
    } catch (e) {
      toaster.toast({ title: tr(STEP_TEXT.steam), body: String(e) });
    }
  }
  busy = "";
  await refresh();
  toaster.toast({
    title: "OBS Game Capture",
    body: failed ? t("Setup finished with errors", "Установка закончилась с ошибками") : t("OBS is ready", "OBS готов"),
  });
}

async function runSetup() {
  busy = "setup";
  notify();
  const r = await startSetup();
  if (!r.ok) {
    busy = "";
    notify();
    return;
  }
  // progress: poll while the backend works; obs_setup_finished ends it
  const timer = setInterval(() => refresh().catch(() => undefined), 1000);
  const done = addEventListener<[SetupState]>("obs_setup_finished", (setup) => {
    clearInterval(timer);
    removeEventListener("obs_setup_finished", done);
    finishSetup(setup);
  });
}

// ---------------- panel ----------------
function useShared(): Ready | null {
  const [, setVersion] = useState(0);
  useEffect(() => {
    const l = () => setVersion((v) => v + 1);
    listeners.add(l);
    refresh().catch(() => undefined);
    return () => {
      listeners.delete(l);
    };
  }, []);
  return current;
}

function Row({ label, ok, text }: { label: string; ok: boolean; text: string }) {
  return (
    <PanelSectionRow>
      <Field label={label} description={text} icon={<span style={{ color: ok ? "#5ba32b" : "#c0392b" }}>●</span>} />
    </PanelSectionRow>
  );
}

function Content() {
  const s = useShared();
  if (!s) {
    return (
      <PanelSection>
        <PanelSectionRow>{t("Loading…", "Загрузка…")}</PanelSectionRow>
      </PanelSection>
    );
  }
  const setup = s.setup;
  const running = busy === "setup" || setup.running;
  const errors = Object.entries(setup.errors) as [SetupStep, string][];
  const ready = !!s.obs && !!s.vkcapture && !!s.layer && s.obs_configured && obsAppid !== null;
  const no = t("not installed", "не установлено");

  return (
    <>
      <PanelSection title={t("Setup", "Установка")}>
        {!s.flatpak && (
          <PanelSectionRow>
            {t("flatpak is not installed on this system: OBS cannot be installed.",
              "На этой системе нет flatpak: OBS не установить.")}
          </PanelSectionRow>
        )}
        <Row label={tr(STEP_TEXT.obs)} ok={!!s.obs} text={s.obs ? `${s.obs.version} (${s.obs.installation})` : no} />
        <Row label={tr(STEP_TEXT.vkcapture)} ok={!!s.vkcapture} text={s.vkcapture ? s.vkcapture.version : no} />
        <Row
          label={tr(STEP_TEXT.layer)}
          ok={!!s.layer}
          text={s.layer === "system" ? t("from the system", "из системы") : s.layer ? t("registered", "подключён") : no}
        />
        <Row
          label={tr(STEP_TEXT.obs_config)}
          ok={s.obs_configured}
          text={
            s.obs_configured
              ? t("Game Capture source, hardware encoding, 1080p60", "Источник Game Capture, аппаратное кодирование, 1080p60")
              : t("not applied yet", "ещё не применены")
          }
        />
        <Row
          label={tr(STEP_TEXT.steam)}
          ok={obsAppid !== null}
          text={obsAppid !== null ? t("in Non-Steam", "в разделе «Сторонние»") : t("not added", "не добавлен")}
        />
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={running || !s.flatpak} onClick={runSetup}>
            {running
              ? `${t("Installing", "Устанавливается")}: ${setup.step ? tr(STEP_TEXT[setup.step]) : "…"}`
              : ready
                ? t("Update and set up again", "Обновить и перенастроить")
                : t("Install and set up", "Установить и настроить")}
          </ButtonItem>
        </PanelSectionRow>
        {s.obs_running && !running && (
          <PanelSectionRow>
            {t("OBS is running: close it before setup, or its settings will not change.",
              "OBS запущен: закрой его перед установкой, иначе настройки не изменятся.")}
          </PanelSectionRow>
        )}
        {!running &&
          errors.map(([step, msg]) => (
            <PanelSectionRow key={step}>
              <Field label={tr(STEP_TEXT[step])} description={msg} />
            </PanelSectionRow>
          ))}
      </PanelSection>

      <PanelSection title={t("Game capture", "Захват игр")}>
        <PanelSectionRow>
          <ToggleField
            label={t("Capture flag in every game", "Флаг захвата во всех играх")}
            description={t(
              "Adds OBS_VKCAPTURE=1 to the launch options of installed games and non-Steam games, new ones within a minute. Off takes it out again.",
              "Добавляет OBS_VKCAPTURE=1 в параметры запуска установленных и сторонних игр, новым — в течение минуты. Выключение убирает его.",
            )}
            checked={s.enabled}
            disabled={!s.layer || busy !== ""}
            onChange={async (on) => {
              busy = "games";
              notify();
              await syncGames(on);
              busy = "";
              notify();
            }}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <Field
            label={t("Games with the flag", "Игр с флагом")}
            description={busy === "games" ? t("updating…", "обновляется…") : undefined}
          >
            {String(s.applied.length)}
          </Field>
        </PanelSectionRow>
        <PanelSectionRow>
          <div style={{ fontSize: "12px", opacity: 0.8 }}>
            {t(
              "Start OBS from the library, then the game: the Game Capture source shows the running game. Switch between them with the Steam button.",
              "Запусти OBS из библиотеки, потом игру: источник Game Capture покажет запущенную игру. Переключайся между ними кнопкой Steam.",
            )}
          </div>
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title={t("Audio", "Звук")}>
        <PanelSectionRow>
          <ToggleField
            label={t("Virtual microphone", "Виртуальный микрофон")}
            description={
              s.virtual_mic && s.virtual_mic_running === false
                ? t("Turned on, but PipeWire has not created it yet: restart the computer.",
                    "Включён, но PipeWire его пока не создал: перезагрузи компьютер.")
                : t(
                    "A silent microphone for when none is connected: without one, Steam's Settings → Audio fails to open. A connected microphone still takes over.",
                    "Пустой микрофон на случай, когда настоящего нет: без него не открываются Настройки → Звук в Steam. Подключённый микрофон всё равно главнее.",
                  )
            }
            checked={s.virtual_mic}
            disabled={busy !== ""}
            onChange={async (on) => {
              busy = "mic";
              notify();
              const r = await setVirtualMic(on);
              if (!r.ok) toaster.toast({ title: t("Virtual microphone", "Виртуальный микрофон"), body: r.error });
              busy = "";
              await refresh();
            }}
          />
        </PanelSectionRow>
      </PanelSection>
    </>
  );
}

export default definePlugin(() => {
  // Plugin loaded (Steam start): new games since the last run get the flag, then a sweep every minute.
  refresh()
    .then((s) => {
      if (s?.enabled) syncGames(true);
    })
    .catch(() => undefined);
  const timer = setInterval(() => {
    if (current?.enabled && busy === "") syncGames(true);
  }, SWEEP_EVERY_MS);

  return {
    name: "OBS Game Capture",
    titleView: <div className={staticClasses.Title}>OBS Game Capture</div>,
    content: <Content />,
    icon: <FaVideo />,
    onDismount() {
      clearInterval(timer);
    },
  };
});

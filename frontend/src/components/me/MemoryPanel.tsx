"use client";

import { useFormatter, useTranslations } from "next-intl";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState, useTransition } from "react";

import { setLocale } from "@/i18n/actions";
import type { Locale } from "@/i18n/config";
import {
  deleteAsk,
  deleteEverything,
  deletePreference,
  deleteView,
  getMe,
  getMemory,
  giveConsent,
  putPreference,
} from "@/lib/api/client";
import type { MemoryView, MeState } from "@/lib/api/types";

const panel = "rounded-card bg-surface p-5";

async function fetchAll(): Promise<{ me: MeState; memory: MemoryView | null }> {
  const me = await getMe();
  return { me, memory: me.consented ? await getMemory() : null };
}
const KEY_LABEL: Record<
  string,
  | "outputLanguage"
  | "uiLanguage"
  | "summaryLength"
  | "topics"
  | "regions"
  | "audio"
> = {
  output_language: "outputLanguage",
  ui_language: "uiLanguage",
  summary_length: "summaryLength",
  followed_topics: "topics",
  followed_regions: "regions",
  audio_preference: "audio",
};
const button =
  "inline-flex h-10 items-center rounded-control px-4 text-sm font-bold";

/**
 * /me (docs/10 section 8, docs/11): consent gate, explicit preferences from closed value sets, every stored item
 * with delete, and "Delete everything". There is no political preference field, by design.
 */
export function MemoryPanel() {
  const t = useTranslations("me");
  const tt = useTranslations("topics");
  const fmt = useFormatter();
  const router = useRouter();
  const [me, setMe] = useState<MeState | null>(null);
  const [memory, setMemory] = useState<MemoryView | null>(null);
  const [status, setStatus] = useState<"idle" | "saved" | "error" | "deleted">(
    "idle",
  );
  const [loadError, setLoadError] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [, startTransition] = useTransition();

  const apply = useCallback((d: { me: MeState; memory: MemoryView | null }) => {
    setMe(d.me);
    setMemory(d.memory);
  }, []);
  const load = useCallback(() => fetchAll().then(apply), [apply]);

  useEffect(() => {
    fetchAll()
      .then(apply)
      .catch(() => setLoadError(true));
  }, [apply]);

  async function save(key: string, value: string | string[]) {
    // Optimistic: the control reflects the choice at once; a failed save reloads the stored truth.
    setMe((m) => (m ? { ...m, preferences: { ...m.preferences, [key]: value } } : m));
    try {
      setMe(await putPreference(key, value));
      setMemory(await getMemory());
      setStatus("saved");
      if (key === "ui_language" && typeof value === "string") {
        startTransition(async () => {
          await setLocale(value as Locale);
          router.refresh();
        });
      }
    } catch {
      setStatus("error");
      await load().catch(() => setLoadError(true));
    }
  }

  async function remove(action: () => Promise<unknown>) {
    await action().catch(() => setStatus("error"));
    await load();
  }

  if (loadError) return <p className="text-ink-muted">{t("loadError")}</p>;
  if (!me)
    return (
      <p aria-busy="true" className="text-ink-muted">
        …
      </p>
    );
  const days = memory?.retention_days ?? 30;

  if (!me.consented) {
    return (
      <section aria-labelledby="consent-heading" className={panel}>
        {status === "deleted" && (
          <p role="status" className="mb-4 font-bold">
            {t("deleted")}
          </p>
        )}
        <h2 id="consent-heading" className="text-2xl">
          {t("consentTitle")}
        </h2>
        <p className="mt-3">{t("consentWhat", { days: 30 })}</p>
        <p className="mt-3">{t("consentNot")}</p>
        <button
          type="button"
          className={`${button} mt-5 bg-ink text-paper hover:bg-ink/85`}
          onClick={async () => {
            await giveConsent();
            setStatus("idle");
            await load();
          }}
        >
          {t("consentButton")}
        </button>
        <p className="mt-2 text-sm text-ink-muted">{t("consentNote")}</p>
      </section>
    );
  }

  const prefs = me.preferences;
  const single = (key: string, label: string) => (
    <label className="flex flex-col gap-1 text-sm font-bold">
      {label}
      <select
        className="h-10 rounded-control border border-ink/25 bg-card px-3 font-normal"
        value={typeof prefs[key] === "string" ? (prefs[key] as string) : ""}
        onChange={(e) =>
          e.target.value
            ? void save(key, e.target.value)
            : void remove(() => deletePreference(key))
        }
      >
        <option value="">{t("notSet")}</option>
        {me.allowed[key].map((v) => (
          <option key={v} value={v}>
            {t(`values.${v}` as "values.en")}
          </option>
        ))}
      </select>
    </label>
  );
  const multi = (key: string, label: string, name: (v: string) => string) => {
    const chosen = new Set(
      Array.isArray(prefs[key]) ? (prefs[key] as string[]) : [],
    );
    return (
      <fieldset>
        <legend className="text-sm font-bold">{label}</legend>
        <ul className="mt-2 flex flex-wrap gap-2">
          {me.allowed[key].map((v) => (
            <li key={v}>
              <label className="inline-flex h-8 cursor-pointer items-center gap-2 rounded-chip bg-card px-3 text-sm">
                <input
                  type="checkbox"
                  checked={chosen.has(v)}
                  onChange={(e) => {
                    const next = new Set(chosen);
                    if (e.target.checked) next.add(v);
                    else next.delete(v);
                    void save(key, [...next]);
                  }}
                />
                {name(v)}
              </label>
            </li>
          ))}
        </ul>
      </fieldset>
    );
  };
  const valueText = (key: string, v: string | string[]) =>
    (Array.isArray(v) ? v : [v])
      .map((x) =>
        key === "followed_topics"
          ? tt(x)
          : key === "followed_regions"
            ? t(`regionNames.${x}` as "regionNames.goa")
            : t(`values.${x}` as "values.en"),
      )
      .join(", ");

  return (
    <div className="flex flex-col gap-8">
      <p role="status" aria-live="polite" className="text-sm font-bold">
        {status === "saved"
          ? t("saved")
          : status === "error"
            ? t("saveError")
            : ""}
      </p>

      <section
        aria-labelledby="prefs-heading"
        className={`${panel} flex flex-col gap-5`}
      >
        <h2 id="prefs-heading" className="text-2xl">
          {t("prefsTitle")}
        </h2>
        <div className="grid gap-4 sm:grid-cols-3">
          {single("output_language", t("outputLanguage"))}
          {single("ui_language", t("uiLanguage"))}
          {single("summary_length", t("summaryLength"))}
        </div>
        {multi("followed_topics", t("topics"), (v) => tt(v))}
        <details>
          <summary className="cursor-pointer text-sm font-bold">
            {t("regions")}
          </summary>
          <div className="mt-2">
            {multi("followed_regions", t("regions"), (v) =>
              t(`regionNames.${v}` as "regionNames.goa"),
            )}
          </div>
        </details>
        <p className="text-sm text-ink-muted">
          {t("audio")}: {t("audioLater")}
        </p>
      </section>

      <section aria-labelledby="stored-heading" className={panel}>
        <h2 id="stored-heading" className="text-2xl">
          {t("storedTitle")}
        </h2>
        <p className="mt-1 text-sm text-ink-muted">
          {t("retention", { days })}
        </p>
        <h3 className="mt-4 text-lg">{t("storedPrefs")}</h3>
        <ul
          className="mt-2 divide-y divide-ink/15"
          data-testid="stored-preferences"
        >
          {Object.entries(memory?.preferences ?? {}).map(([k, v]) => (
            <li
              key={k}
              className="flex items-center justify-between gap-4 py-2 text-sm"
            >
              <span>
                <b>{KEY_LABEL[k] ? t(KEY_LABEL[k]) : k}</b>: {valueText(k, v)}
              </span>
              <button
                type="button"
                className="font-bold underline"
                onClick={() => void remove(() => deletePreference(k))}
              >
                {t("delete")}
              </button>
            </li>
          ))}
          {Object.keys(memory?.preferences ?? {}).length === 0 && (
            <li className="py-2 text-sm text-ink-muted">{t("nothing")}</li>
          )}
        </ul>
        <h3 className="mt-4 text-lg">{t("storedViews")}</h3>
        <ul className="mt-2 divide-y divide-ink/15">
          {(memory?.story_views ?? []).map((v) => (
            <li
              key={v.id}
              className="flex items-center justify-between gap-4 py-2 text-sm"
            >
              <span>
                <Link href={`/story/${v.story_id}`} className="underline">
                  {v.headline}
                </Link>{" "}
                <span className="text-ink-muted">
                  {fmt.dateTime(new Date(v.viewed_at), { dateStyle: "medium" })}
                </span>
              </span>
              <button
                type="button"
                className="font-bold underline"
                onClick={() => void remove(() => deleteView(v.id))}
              >
                {t("delete")}
              </button>
            </li>
          ))}
          {(memory?.story_views ?? []).length === 0 && (
            <li className="py-2 text-sm text-ink-muted">{t("nothing")}</li>
          )}
        </ul>
        <h3 className="mt-4 text-lg">{t("storedAsks")}</h3>
        <ul className="mt-2 divide-y divide-ink/15">
          {(memory?.ask_history ?? []).map((a) => (
            <li
              key={a.id}
              className="flex items-center justify-between gap-4 py-2 text-sm"
            >
              <span>
                {a.question}{" "}
                <span className="text-ink-muted">
                  {fmt.dateTime(new Date(a.created_at), {
                    dateStyle: "medium",
                  })}
                </span>
              </span>
              <button
                type="button"
                className="font-bold underline"
                onClick={() => void remove(() => deleteAsk(a.id))}
              >
                {t("delete")}
              </button>
            </li>
          ))}
          {(memory?.ask_history ?? []).length === 0 && (
            <li className="py-2 text-sm text-ink-muted">{t("nothing")}</li>
          )}
        </ul>
      </section>

      <section className={panel}>
        {!confirming ? (
          <button
            type="button"
            className={`${button} bg-flag-bg text-flag-ink`}
            onClick={() => setConfirming(true)}
          >
            {t("deleteEverything")}
          </button>
        ) : (
          <div
            role="alertdialog"
            aria-labelledby="delete-confirm"
            className="flex flex-col gap-3"
          >
            <p id="delete-confirm">{t("deleteConfirm")}</p>
            <div className="flex gap-3">
              <button
                type="button"
                className={`${button} bg-ink text-paper`}
                onClick={async () => {
                  await deleteEverything();
                  setConfirming(false);
                  setStatus("deleted");
                  await load();
                }}
              >
                {t("deleteYes")}
              </button>
              <button
                type="button"
                className={`${button} border border-ink/25`}
                onClick={() => setConfirming(false)}
              >
                {t("deleteNo")}
              </button>
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

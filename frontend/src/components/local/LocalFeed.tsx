"use client";

import { useLocale, useMessages, useTranslations } from "next-intl";
import { useCallback, useEffect, useState, useSyncExternalStore } from "react";

import { EmptyState } from "@/components/states/EmptyState";
import { FeedGrid } from "@/components/story/FeedLayout";
import { getFeed } from "@/lib/api/client";
import type { StoryCard } from "@/lib/api/types";
import { stateAt, type StateShapes } from "@/lib/geo";

const KEY = "lens.local.state";

type Status = "idle" | "locating" | "denied" | "unsupported" | "outside" | "failed";

function saved(): string | null {
  try {
    return localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

const subscribe = (onChange: () => void) => {
  window.addEventListener("storage", onChange);
  return () => window.removeEventListener("storage", onChange);
};

type Loaded = { state: string; items: StoryCard[]; cursor: string | null } | { state: string; failed: true };

/** Local tab (F-15): the reader's state from browser location, resolved on the device (only the state
 * slug reaches the API), or picked by hand. The choice is kept in this browser only. */
export function LocalFeed() {
  const t = useTranslations("local");
  const tr = useTranslations("me");
  const locale = useLocale();
  const names = (useMessages() as { me: { regionNames: Record<string, string> } }).me.regionNames;
  const stored = useSyncExternalStore(subscribe, saved, () => null);
  const [picked, setPicked] = useState<string | null>(null);
  const state = picked ?? (stored && stored in names ? stored : null);
  const [status, setStatus] = useState<Status>("idle");
  const [loaded, setLoaded] = useState<Loaded | null>(null);

  const choose = useCallback((slug: string) => {
    setStatus("idle");
    setPicked(slug);
    try {
      localStorage.setItem(KEY, slug);
    } catch {
      /* storage blocked: the choice lasts this visit */
    }
  }, []);

  /** Asks the browser for a position (it prompts on first use) and resolves the state on the device. */
  const request = useCallback(() => {
    navigator.geolocation.getCurrentPosition(
      async ({ coords }) => {
        try {
          const shapes = (await (await fetch("/geo/india-states.json")).json()) as StateShapes;
          const slug = stateAt(coords.longitude, coords.latitude, shapes);
          if (slug) choose(slug);
          else setStatus("outside");
        } catch {
          setStatus("failed");
        }
      },
      (e) => setStatus(e.code === e.PERMISSION_DENIED ? "denied" : "failed"),
      { enableHighAccuracy: false, timeout: 10_000, maximumAge: 3_600_000 },
    );
  }, [choose]);

  const locate = () => {
    if (!("geolocation" in navigator)) return setStatus("unsupported");
    setStatus("locating");
    request();
  };

  useEffect(() => {
    if (!saved() && "geolocation" in navigator) request(); // first visit: the browser asks for permission
  }, [request]);

  useEffect(() => {
    if (!state) return;
    let live = true;
    getFeed({ tab: "local", state, lang: locale })
      .then((p) => live && setLoaded({ state, items: p.items, cursor: p.next_cursor }))
      .catch(() => live && setLoaded({ state, failed: true }));
    return () => {
      live = false;
    };
  }, [state, locale]);

  const current = loaded?.state === state ? loaded : null; // a result for another state is stale
  const error = current !== null && "failed" in current;
  const items = current && !("failed" in current) ? current.items : null;
  const cursor = current && !("failed" in current) ? current.cursor : null;

  const more = () => {
    if (!cursor || !state || !items) return;
    getFeed({ tab: "local", state, lang: locale, cursor })
      .then((p) => setLoaded({ state, items: [...items, ...p.items], cursor: p.next_cursor }))
      .catch(() => setLoaded({ state, failed: true }));
  };

  const sorted = Object.entries(names).sort((a, b) => a[1].localeCompare(b[1], locale));

  return (
    <div>
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-sm font-bold">
          {t("pick")}
          <select
            className="h-11 rounded-control border border-ink/25 bg-paper px-3 font-normal"
            value={state ?? ""}
            onChange={(e) => e.target.value && choose(e.target.value)}
          >
            <option value="" disabled>
              {t("pickPlaceholder")}
            </option>
            {sorted.map(([slug, name]) => (
              <option key={slug} value={slug}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          onClick={locate}
          disabled={status === "locating"}
          className="h-11 rounded-control bg-ink px-5 font-bold text-paper hover:bg-ink/85 disabled:opacity-60"
        >
          {status === "locating" ? t("locating") : t("useLocation")}
        </button>
      </div>
      <p className="mt-2 text-sm text-ink-muted">{t("privacy")}</p>
      {status !== "idle" && status !== "locating" && (
        <p role="status" className="mt-3 rounded-card bg-surface p-4">
          {t(status)}
        </p>
      )}

      <div className="mt-6">
        {state && <h2 className="mb-2 text-2xl">{tr(`regionNames.${state}` as "regionNames.goa")}</h2>}
        {error && <p role="alert">{t("error")}</p>}
        {state && !error && items === null && (
          <p aria-busy="true" className="text-ink-muted">
            …
          </p>
        )}
        {items && items.length === 0 && <EmptyState>{t("empty")}</EmptyState>}
        {items && items.length > 0 && <FeedGrid stories={items} />}
        {cursor && (
          <div className="mt-8 flex justify-center">
            <button type="button" onClick={more} className="h-11 rounded-control border border-ink/25 px-5 font-bold">
              {t("more")}
            </button>
          </div>
        )}
      </div>
      <p className="mt-10 text-xs text-ink-muted">
        {t("attribution")}{" "}
        <a className="underline" href="https://github.com/datameet/maps" rel="noopener noreferrer" target="_blank">
          DataMeet India
        </a>{" "}
        (
        <a
          className="underline"
          href="https://creativecommons.org/licenses/by/4.0/"
          rel="noopener noreferrer"
          target="_blank"
        >
          CC BY 4.0
        </a>
        )
      </p>
    </div>
  );
}

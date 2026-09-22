"use client";

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState, useTransition } from "react";

import { loadFeedPage } from "@/app/actions";
import type { StoryCard as StoryCardData } from "@/lib/api/types";

import { StoryCard } from "./StoryCard";

/** Infinite scroll with a visible "Load more" fallback (docs/10). */
export function FeedMore({ initialCursor, topic }: { initialCursor: string | null; topic?: string }) {
  const t = useTranslations("home");
  const [items, setItems] = useState<StoryCardData[]>([]);
  const [cursor, setCursor] = useState(initialCursor);
  const [failed, setFailed] = useState(false);
  const [pending, startTransition] = useTransition();
  const sentinel = useRef<HTMLDivElement>(null);

  const load = useCallback(() => {
    if (!cursor || pending) return;
    startTransition(async () => {
      try {
        const page = await loadFeedPage(cursor, topic);
        setItems((prev) => [...prev, ...page.items]);
        setCursor(page.next_cursor);
        setFailed(false);
      } catch {
        setFailed(true);
      }
    });
  }, [cursor, pending, topic]);

  useEffect(() => {
    const el = sentinel.current;
    if (!el || !cursor || failed) return;
    const io = new IntersectionObserver((entries) => entries.some((e) => e.isIntersecting) && load(), {
      rootMargin: "400px",
    });
    io.observe(el);
    return () => io.disconnect();
  }, [cursor, failed, load]);

  return (
    <>
      {items.length > 0 && (
        <div className="grid gap-x-10 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((s) => (
            <div key={s.id} className="border-b border-ink/15 py-5">
              <StoryCard story={s} />
            </div>
          ))}
        </div>
      )}
      <div ref={sentinel} className="mt-8 flex flex-col items-center gap-2 text-sm" aria-live="polite">
        {failed && <p role="alert">{t("loadMoreError")}</p>}
        {cursor ? (
          <button
            type="button"
            onClick={load}
            disabled={pending}
            className="h-11 rounded-control border border-ink px-6 font-bold hover:bg-ink hover:text-paper disabled:opacity-60"
          >
            {pending ? t("loadingMore") : t("loadMore")}
          </button>
        ) : (
          items.length > 0 && <p className="text-ink-muted">{t("end")}</p>
        )}
      </div>
    </>
  );
}

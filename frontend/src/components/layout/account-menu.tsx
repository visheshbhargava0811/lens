"use client";

import { ChevronDown, UserRound } from "lucide-react";
import { useTranslations } from "next-intl";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { getMe, putPreference, signOut } from "@/lib/api/client";
import type { MeState } from "@/lib/api/types";

const select =
  "h-10 rounded-control border border-ink/25 bg-card px-3 text-sm font-normal";
const textAction = "font-bold underline decoration-ink/40 hover:decoration-ink";

/** Header account control (ADR-0044): "Sign in" until signed in, then a panel with quick preferences,
 * links to For you and the full /me page, and Sign out. Preferences use the same closed value sets as /me. */
export function AccountMenu({ signInLabel }: { signInLabel: string }) {
  const t = useTranslations("account");
  const tm = useTranslations("me");
  const tt = useTranslations("topics");
  const router = useRouter();
  const [me, setMe] = useState<MeState | null>(null);
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<"" | "saved" | "error" | "signOutError">(
    "",
  );

  useEffect(() => {
    getMe()
      .then(setMe)
      .catch(() => setMe(null));
  }, []);

  if (!me?.signed_in_with)
    return (
      <Link
        href="/sign-in"
        className="hidden h-10 items-center rounded-control bg-ink px-5 text-sm font-bold whitespace-nowrap text-paper hover:bg-ink/85 md:inline-flex"
      >
        {signInLabel}
      </Link>
    );

  const prefs = me.preferences;
  async function save(key: string, value: string | string[]) {
    setMe((m) =>
      m ? { ...m, preferences: { ...m.preferences, [key]: value } } : m,
    ); // optimistic
    try {
      setMe(await putPreference(key, value));
      setStatus("saved");
    } catch {
      setStatus("error");
      setMe(await getMe().catch(() => me));
    }
  }
  const topics = new Set(
    Array.isArray(prefs.followed_topics) ? prefs.followed_topics : [],
  );
  const single = (key: string, label: string) => (
    <label className="flex flex-col gap-1 text-sm font-bold">
      {label}
      <select
        className={select}
        value={typeof prefs[key] === "string" ? (prefs[key] as string) : ""}
        onChange={(e) => e.target.value && void save(key, e.target.value)}
      >
        <option value="" disabled>
          {tm("notSet")}
        </option>
        {me.allowed[key].map((v) => (
          <option key={v} value={v}>
            {tm(`values.${v}` as "values.en")}
          </option>
        ))}
      </select>
    </label>
  );

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        aria-label={t("menu")}
        className="inline-flex h-10 items-center gap-2 rounded-control border border-ink/25 bg-card px-3 text-sm font-bold hover:border-ink/60 data-[popup-open]:border-ink"
      >
        <UserRound aria-hidden className="size-4" />
        <span className="hidden md:inline">{t("menu")}</span>
        <ChevronDown aria-hidden className="size-4 text-ink-muted" />
      </PopoverTrigger>
      <PopoverContent
        align="end"
        className="w-80 gap-4 p-4"
        aria-label={t("menu")}
        data-testid="account-menu"
      >
        <p className="text-xs font-medium text-ink-muted">
          {t("signedInWith")}
        </p>
        <section
          aria-labelledby="account-quick"
          className="flex flex-col gap-3"
        >
          <div className="flex items-baseline justify-between gap-2">
            <h2 id="account-quick" className="text-base">
              {t("quick")}
            </h2>
            <p role="status" aria-live="polite" className="text-xs font-bold">
              {status === "saved"
                ? tm("saved")
                : status === "error"
                  ? tm("saveError")
                  : status === "signOutError"
                    ? t("signOutError")
                    : ""}
            </p>
          </div>
          <div className="grid grid-cols-2 gap-3">
            {single("output_language", tm("outputLanguage"))}
            {single("summary_length", tm("summaryLength"))}
          </div>
          <fieldset>
            <legend className="text-sm font-bold">{tm("topics")}</legend>
            <ul className="mt-2 flex flex-wrap gap-1.5">
              {me.allowed.followed_topics.map((v) => (
                <li key={v}>
                  <label className="inline-flex h-7 cursor-pointer items-center gap-1.5 rounded-chip bg-surface px-2 text-[13px] font-bold has-[:checked]:bg-ink has-[:checked]:text-paper has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-ink">
                    <input
                      type="checkbox"
                      className="sr-only"
                      checked={topics.has(v)}
                      onChange={(e) => {
                        const next = new Set(topics);
                        if (e.target.checked) next.add(v);
                        else next.delete(v);
                        void save("followed_topics", [...next]);
                      }}
                    />
                    {tt(v)}
                  </label>
                </li>
              ))}
            </ul>
          </fieldset>
        </section>
        <nav
          aria-label={t("menu")}
          className="flex flex-col gap-2 border-t border-ink/10 pt-3 text-sm"
        >
          <Link
            href="/for-you"
            onClick={() => setOpen(false)}
            className={textAction}
          >
            {t("forYou")}
          </Link>
          <Link
            href="/me"
            onClick={() => setOpen(false)}
            className={textAction}
          >
            {t("all")}
          </Link>
        </nav>
        <button
          type="button"
          className="h-10 w-full rounded-control border border-ink/25 text-sm font-bold hover:border-ink/60"
          onClick={async () => {
            try {
              await signOut();
              setOpen(false);
              setMe(await getMe());
              router.refresh();
            } catch {
              setStatus("signOutError");
            }
          }}
        >
          {t("signOut")}
        </button>
      </PopoverContent>
    </Popover>
  );
}

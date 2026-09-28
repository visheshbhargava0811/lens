"use client";

import { useTranslations } from "next-intl";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { getMe, signInUrl } from "@/lib/api/client";
import type { MeState } from "@/lib/api/types";

const ERRORS = ["cancelled", "state", "expired", "provider"] as const;

/** A path on this site only; anything else falls back to /me (the API checks again). */
function safeNext(v: string | null): string {
  return v && v.startsWith("/") && !v.startsWith("//") && !v.includes("\\")
    ? v
    : "/me";
}

function GoogleMark() {
  // Google's "G" mark, as its sign-in branding guidelines ask for on a custom button.
  return (
    <svg aria-hidden viewBox="0 0 48 48" className="size-5">
      <path
        fill="#EA4335"
        d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"
      />
      <path
        fill="#4285F4"
        d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"
      />
      <path
        fill="#FBBC05"
        d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"
      />
      <path
        fill="#34A853"
        d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"
      />
    </svg>
  );
}

/** /sign-in (ADR-0044): Google, with what signing in does and what Lens receives stated before the button. */
export function SignInPanel() {
  const t = useTranslations("signIn");
  const params = useSearchParams();
  const error = ERRORS.find((e) => e === params.get("error"));
  const next = safeNext(params.get("next"));
  const [me, setMe] = useState<MeState | null>(null);

  useEffect(() => {
    getMe()
      .then(setMe)
      .catch(() => setMe(null));
  }, []);

  if (me?.signed_in_with)
    return (
      <p className="rounded-card bg-surface p-5">
        {t("signedIn")}{" "}
        <Link
          href="/me"
          className="font-bold underline decoration-ink/40 hover:decoration-ink"
        >
          {t("toPrefs")}
        </Link>
      </p>
    );

  const available = me === null || me.sign_in_providers.includes("google");
  return (
    <div className="flex max-w-[60ch] flex-col gap-6">
      {error && (
        <p
          role="alert"
          className="rounded-card bg-flag-bg p-4 font-medium text-flag-ink"
        >
          {t(`errors.${error}`)}
        </p>
      )}
      {available ? (
        <a
          href={signInUrl(next)}
          className="inline-flex h-11 w-fit items-center gap-3 rounded-control border border-ink/25 bg-card px-5 font-bold hover:border-ink/60"
        >
          <GoogleMark />
          {t("google")}
        </a>
      ) : (
        <p className="rounded-card bg-surface p-4">{t("unavailable")}</p>
      )}
      <p className="text-sm text-ink-muted">{t("consent")}</p>

      <section
        aria-labelledby="signin-what"
        className="rounded-card bg-surface p-5"
      >
        <h2 id="signin-what" className="text-xl">
          {t("whatTitle")}
        </h2>
        <ul className="mt-3 list-disc space-y-1 ps-5 marker:text-ink-muted">
          <li>{t("what1")}</li>
          <li>{t("what2")}</li>
          <li>{t("what3")}</li>
        </ul>
        <h2 className="mt-5 text-xl">{t("getsTitle")}</h2>
        <p className="mt-2">{t("gets")}</p>
      </section>

      <Link
        href="/me"
        className="w-fit font-bold underline decoration-ink/40 hover:decoration-ink"
      >
        {t("anonymous")}
      </Link>
    </div>
  );
}

import { getRequestConfig } from "next-intl/server";
import { cookies } from "next/headers";

import { defaultLocale, isLocale, LOCALE_COOKIE } from "./config";

// UI language comes from a cookie, not the URL (docs/DECISIONS.md, ADR-0003).
export default getRequestConfig(async () => {
  const store = await cookies();
  const fromCookie = store.get(LOCALE_COOKIE)?.value;
  const locale = isLocale(fromCookie) ? fromCookie : defaultLocale;
  return {
    locale,
    timeZone: "Asia/Kolkata",
    now: new Date(),
    messages: (await import(`../../messages/${locale}.json`)).default,
  };
});

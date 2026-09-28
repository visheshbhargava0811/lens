import { getTranslations } from "next-intl/server";
import { Suspense } from "react";

import { SignInPanel } from "@/components/me/SignInPanel";

/** Google sign-in (ADR-0044). The anonymous profile on /me (ADR-0041) still works without an account. */
export default async function SignInPage() {
  const t = await getTranslations("signIn");
  return (
    <div className="mx-auto flex max-w-xl flex-col items-center py-6 text-center md:py-12">
      <h1 className="text-3xl md:text-4xl">{t("title")}</h1>
      <p className="mt-2 text-lg text-ink-muted">{t("intro")}</p>
      <div className="mt-8 w-full">
        <Suspense>
          <SignInPanel />
        </Suspense>
      </div>
    </div>
  );
}

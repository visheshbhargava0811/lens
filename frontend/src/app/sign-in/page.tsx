import { getTranslations } from "next-intl/server";
import { Suspense } from "react";

import { SignInPanel } from "@/components/me/SignInPanel";

/** Google sign-in (ADR-0044). The anonymous profile on /me (ADR-0041) still works without an account. */
export default async function SignInPage() {
  const t = await getTranslations("signIn");
  return (
    <div>
      <h1 className="text-3xl">{t("title")}</h1>
      <p className="mt-2 text-lg text-ink-muted">{t("intro")}</p>
      <div className="mt-6">
        <Suspense>
          <SignInPanel />
        </Suspense>
      </div>
    </div>
  );
}

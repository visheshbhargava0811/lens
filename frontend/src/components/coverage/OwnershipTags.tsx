import { useTranslations } from "next-intl";

import type { Ownership } from "@/lib/api/types";

import { MethodologyLink } from "./MethodologyLink";

/** Grouped by parent owner. The Unknown bucket is shown honestly. */
export function OwnershipTags({ ownership }: { ownership: Ownership }) {
  const t = useTranslations();
  return (
    <div>
      <ul className="space-y-1 text-sm">
        {ownership.groups.map((g) => (
          <li key={g.name} className="flex justify-between gap-3">
            <span>{g.name}</span>
            <span className="tabular-nums text-ink-muted">{t("coverage.sources", { count: g.sources })}</span>
          </li>
        ))}
        {ownership.unknown > 0 && (
          <li className="flex justify-between gap-3">
            <span>{t("ownership.unknown")}</span>
            <span className="tabular-nums text-ink-muted">{t("coverage.sources", { count: ownership.unknown })}</span>
          </li>
        )}
      </ul>
      <MethodologyLink href={ownership.methodology_url} className="mt-2 inline-block">
        {t("coverage.howCalculated")}
      </MethodologyLink>
    </div>
  );
}

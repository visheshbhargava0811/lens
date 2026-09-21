import { useTranslations } from "next-intl";

const block = "animate-pulse rounded-control bg-surface motion-reduce:animate-none";

export function StoryCardSkeleton({ variant = "standard" }: { variant?: "hero" | "standard" }) {
  return (
    <div aria-hidden className={variant === "standard" ? "space-y-3 rounded-card border p-4" : "space-y-4"}>
      <div className={`${block} ${variant === "hero" ? "h-10 w-4/5" : "h-6 w-11/12"}`} />
      {variant === "hero" && <div className={`${block} h-10 w-3/5`} />}
      <div className={`${block} ${variant === "hero" ? "h-3" : "h-2"} w-full rounded-chip`} />
      <div className={`${block} h-3 w-1/2`} />
    </div>
  );
}

export function FeedSkeleton() {
  const t = useTranslations("states");
  return (
    <div role="status" aria-live="polite" className="space-y-8">
      <span className="sr-only">{t("loading")}</span>
      <StoryCardSkeleton variant="hero" />
      <div className="grid gap-4 sm:grid-cols-2">
        {Array.from({ length: 4 }, (_, i) => (
          <StoryCardSkeleton key={i} />
        ))}
      </div>
    </div>
  );
}

export function StorySkeleton() {
  const t = useTranslations("states");
  return (
    <div role="status" aria-live="polite" className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_340px]">
      <span className="sr-only">{t("loading")}</span>
      <div className="space-y-4">
        <div className={`${block} h-10 w-11/12`} />
        <div className={`${block} h-10 w-2/3`} />
        <div className={`${block} mt-6 h-5 w-full`} />
        <div className={`${block} h-5 w-full`} />
        <div className={`${block} h-5 w-4/5`} />
      </div>
      <div className="space-y-3 rounded-card border p-4">
        <div className={`${block} h-5 w-1/3`} />
        <div className={`${block} h-3.5 w-full rounded-chip`} />
        <div className={`${block} h-16 w-full`} />
      </div>
    </div>
  );
}

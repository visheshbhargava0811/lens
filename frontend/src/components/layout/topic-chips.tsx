"use client";

import { TrendingUp } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

type Props = { label: string; items: { key: string; label: string }[] };

export function TopicChips({ label, items }: Props) {
  const pathname = usePathname();
  const active = pathname === "/" ? "top" : pathname.startsWith("/topic/") ? pathname.split("/")[2] : null;
  return (
    <nav aria-label={label} className="border-t">
      <div className="mx-auto flex max-w-[1280px] items-center gap-3 px-4 md:px-6">
        <TrendingUp aria-hidden className="size-4 shrink-0 text-ink-muted" />
        <ul className="flex gap-2 overflow-x-auto py-2.5 [scrollbar-width:none]">
          {items.map((item) => {
            const isActive = item.key === active;
            return (
              <li key={item.key} className="shrink-0">
                <Link
                  href={item.key === "top" ? "/" : `/topic/${item.key}`}
                  aria-current={isActive ? "page" : undefined}
                  className={cn(
                    "inline-flex h-7 items-center rounded-chip px-2.5 text-[0.8125rem] font-bold",
                    isActive ? "bg-ink text-paper" : "bg-surface text-ink hover:bg-line",
                  )}
                >
                  {item.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </div>
    </nav>
  );
}

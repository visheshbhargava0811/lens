"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

type Props = { label: string; items: { key: string; label: string }[] };

export function TopicChips({ label, items }: Props) {
  const pathname = usePathname();
  const active = pathname === "/" ? "top" : pathname.startsWith("/topic/") ? pathname.split("/")[2] : null;
  return (
    <nav aria-label={label} className="border-t">
      <ul className="mx-auto flex max-w-[1200px] gap-2 overflow-x-auto px-4 py-2 [scrollbar-width:none] md:px-6">
        {items.map((item) => {
          const isActive = item.key === active;
          return (
            <li key={item.key} className="shrink-0">
              <Link
                href={item.key === "top" ? "/" : `/topic/${item.key}`}
                aria-current={isActive ? "page" : undefined}
                className={cn(
                  "inline-flex h-8 items-center rounded-chip px-3 text-sm font-medium",
                  isActive ? "bg-ink text-paper" : "bg-surface text-ink hover:bg-line",
                )}
              >
                {item.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

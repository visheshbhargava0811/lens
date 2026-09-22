"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

/** Primary nav with an ink underline on the current section. */
export function NavLinks({ label, items }: { label: string; items: { href: string; label: string }[] }) {
  const pathname = usePathname();
  const isActive = (href: string) => (href === "/" ? pathname === "/" || pathname.startsWith("/topic/") : pathname.startsWith(href));
  return (
    <nav aria-label={label} className="hidden self-stretch md:block">
      <ul className="flex h-full items-stretch gap-6 text-[0.9375rem] font-medium whitespace-nowrap">
        {items.map((item) => {
          const active = isActive(item.href);
          return (
            <li key={item.href} className="flex">
              <Link
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "flex items-center border-b-[3px] pt-[3px]",
                  active ? "border-ink text-ink" : "border-transparent text-ink/75 hover:text-ink",
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

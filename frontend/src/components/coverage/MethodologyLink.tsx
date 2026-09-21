import Link from "next/link";

import { cn } from "@/lib/utils";

/** Always present near any bar or rating (docs/10). Sits above a card's stretched link. */
export function MethodologyLink({
  href,
  children,
  className,
}: {
  href: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <Link
      href={href}
      className={cn("relative z-10 text-xs font-medium text-link underline-offset-2 hover:underline", className)}
    >
      {children}
    </Link>
  );
}

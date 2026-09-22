import type { Metadata } from "next";
import Link from "next/link";
import { Noto_Sans, Noto_Sans_Devanagari } from "next/font/google";
import { NextIntlClientProvider } from "next-intl";
import { getLocale, getTranslations } from "next-intl/server";

import { BottomTabBar } from "@/components/layout/bottom-tab-bar";
import { SiteHeader } from "@/components/layout/site-header";
import { MockProvider } from "@/mocks/mock-provider";

import "./globals.css";

const notoSans = Noto_Sans({
  subsets: ["latin", "latin-ext"],
  weight: ["400", "500", "700", "800"],
  variable: "--font-noto-sans",
  display: "swap",
});

// More Noto script families (Bengali, Tamil, ...) are added with each launch language.
const notoDevanagari = Noto_Sans_Devanagari({
  subsets: ["devanagari"],
  weight: ["400", "500", "700", "800"],
  variable: "--font-noto-devanagari",
  display: "swap",
});

export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("meta");
  return { title: t("title"), description: t("description") };
}

export default async function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const locale = await getLocale();
  const t = await getTranslations("nav");
  const tm = await getTranslations("meta");
  const tf = await getTranslations("methodology");
  return (
    <html lang={locale} className={`${notoSans.variable} ${notoDevanagari.variable}`}>
      <body className="flex min-h-dvh flex-col">
        <NextIntlClientProvider>
          <MockProvider>
            <a
              href="#main"
              className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-2 focus:z-50 focus:rounded-control focus:bg-paper focus:px-3 focus:py-2"
            >
              {t("skipToContent")}
            </a>
            <SiteHeader />
            <main id="main" tabIndex={-1} className="outline-none mx-auto w-full max-w-[1280px] flex-1 px-4 pb-16 pt-8 md:px-6 md:pt-10">
              {children}
            </main>
            <footer className="mt-8 bg-strip pb-24 text-strip-ink md:pb-0">
              <div className="mx-auto flex max-w-[1280px] flex-wrap items-baseline gap-x-8 gap-y-2 px-4 py-8 md:px-6">
                <Link href="/" lang="en" className="text-2xl font-extrabold tracking-[-0.04em] text-paper">
                  Lens
                </Link>
                <p className="text-sm">{tm("description")}</p>
                <Link href="/methodology" className="text-sm font-bold underline decoration-strip-ink/40 hover:decoration-strip-ink md:ms-auto">
                  {tf("heading")}
                </Link>
              </div>
            </footer>
            <BottomTabBar />
          </MockProvider>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}

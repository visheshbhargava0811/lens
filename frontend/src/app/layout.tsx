import type { Metadata } from "next";
import { Noto_Sans, Noto_Sans_Devanagari } from "next/font/google";
import { NextIntlClientProvider } from "next-intl";
import { getLocale, getTranslations } from "next-intl/server";

import { BottomTabBar } from "@/components/layout/bottom-tab-bar";
import { SiteHeader } from "@/components/layout/site-header";
import { MockProvider } from "@/mocks/mock-provider";

import "./globals.css";

const notoSans = Noto_Sans({
  subsets: ["latin", "latin-ext"],
  weight: ["400", "500", "700"],
  variable: "--font-noto-sans",
  display: "swap",
});

// More Noto script families (Bengali, Tamil, ...) are added with each launch language.
const notoDevanagari = Noto_Sans_Devanagari({
  subsets: ["devanagari"],
  weight: ["400", "500", "700"],
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
  return (
    <html lang={locale} className={`${notoSans.variable} ${notoDevanagari.variable}`}>
      <body className="min-h-dvh">
        <NextIntlClientProvider>
          <MockProvider>
            <a
              href="#main"
              className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-2 focus:z-50 focus:rounded-control focus:bg-paper focus:px-3 focus:py-2"
            >
              {t("skipToContent")}
            </a>
            <SiteHeader />
            <main id="main" tabIndex={-1} className="outline-none mx-auto w-full max-w-[1200px] px-4 pb-24 pt-6 md:px-6 md:pb-12">
              {children}
            </main>
            <BottomTabBar />
          </MockProvider>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}

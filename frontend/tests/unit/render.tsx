import { render } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import type { ReactElement } from "react";

import en from "../../messages/en.json";

export const NOW = new Date("2026-09-21T12:00:00Z");

export function renderWithIntl(ui: ReactElement) {
  return render(
    <NextIntlClientProvider locale="en" messages={en} timeZone="Asia/Kolkata" now={NOW}>
      {ui}
    </NextIntlClientProvider>,
  );
}

/** Language name in the UI locale, e.g. ("hi", "en") -> "Hindi", ("en", "hi") -> "अंग्रेज़ी". */
export function languageName(code: string, uiLocale: string): string {
  try {
    const base = code.split("-")[0];
    return new Intl.DisplayNames([uiLocale], { type: "language" }).of(base) ?? code;
  } catch {
    return code;
  }
}

/** Language counts, largest first. */
export function sortedLanguages(byLanguage: Record<string, number>): [string, number][] {
  return Object.entries(byLanguage).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
}

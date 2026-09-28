/**
 * External links and images come from ingested feeds and APIs. Only http(s) URLs are ever rendered, so a
 * `javascript:` or `data:` URL cannot become a clickable script (XSS). The backend enforces the same rule at
 * ingest; this is the second layer.
 */
export function safeUrl(url: string | null | undefined): string | undefined {
  if (!url) return undefined;
  if (url.startsWith("/") && !url.startsWith("//")) return url; // our own pages (methodology anchors)
  try {
    const u = new URL(url);
    return u.protocol === "https:" || u.protocol === "http:"
      ? u.toString()
      : undefined;
  } catch {
    return undefined;
  }
}

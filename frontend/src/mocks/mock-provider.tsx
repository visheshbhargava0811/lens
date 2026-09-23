"use client";

/**
 * Starts the MSW service worker for browser-side fetches when NEXT_PUBLIC_API_MOCKING=enabled.
 * Never blocks rendering: pages are server-rendered and their data is mocked in instrumentation.ts.
 * Started when this module loads (before any component effect runs), and client fetches (Ask)
 * await `__lensMocksReady`, so none can race past the worker.
 */
if (typeof window !== "undefined" && process.env.NEXT_PUBLIC_API_MOCKING === "enabled") {
  (globalThis as { __lensMocksReady?: Promise<unknown> }).__lensMocksReady = import("./browser").then(({ worker }) =>
    worker.start({ onUnhandledRequest: "bypass", quiet: true }),
  );
}

export function MockProvider({ children }: { children: React.ReactNode }) {
  return children;
}

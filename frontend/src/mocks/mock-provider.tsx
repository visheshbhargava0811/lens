"use client";

import { useEffect } from "react";

/**
 * Starts the MSW service worker for browser-side fetches when NEXT_PUBLIC_API_MOCKING=enabled.
 * Never blocks rendering: pages are server-rendered and their data is mocked in instrumentation.ts.
 */
export function MockProvider({ children }: { children: React.ReactNode }) {
  useEffect(() => {
    if (process.env.NEXT_PUBLIC_API_MOCKING !== "enabled") return;
    void import("./browser").then(({ worker }) => worker.start({ onUnhandledRequest: "bypass", quiet: true }));
  }, []);
  return children;
}

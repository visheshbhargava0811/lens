/** Serves MSW fixtures to server-side fetches when NEXT_PUBLIC_API_MOCKING=enabled (docs/12, Phase 1B). */
export async function register() {
  if (process.env.NEXT_RUNTIME === "nodejs" && process.env.NEXT_PUBLIC_API_MOCKING === "enabled") {
    const { server } = await import("./mocks/node");
    server.listen({ onUnhandledRequest: "bypass" });
    console.log("[lens] API mocking enabled (MSW fixtures)");
  }
}

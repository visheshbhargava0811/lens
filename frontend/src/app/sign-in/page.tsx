import { redirect } from "next/navigation";

/** Lens has no accounts yet (ADR-0041): personalization is an anonymous, consented profile managed on /me. */
export default function Page() {
  redirect("/me");
}

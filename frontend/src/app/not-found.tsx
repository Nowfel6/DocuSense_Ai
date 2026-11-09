import { RouteState } from "@/components/ui/feedback";

export default function NotFound() {
  return (
    <main className="ds-public-content" id="main-content">
      <RouteState
        kind="not-found"
        title="Page not found"
        message="This page is unavailable or you may not have access to it."
        href="/"
        actionLabel="Return home"
      />
    </main>
  );
}

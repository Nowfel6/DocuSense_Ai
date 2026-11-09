"use client";

import { useEffect, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import { usePathname, useRouter } from "next/navigation";

import type { SessionProfile } from "@/lib/auth/session-types";

import { GlobalSidebar, MobileNavigationDrawer } from "./global-sidebar";
import { breadcrumbsForPathname, navigationForRole } from "./navigation";
import { TopContextBar, type BreadcrumbItem } from "./top-context-bar";
import { SkipLink } from "./skip-link";

const COLLAPSE_KEY = "docusense.sidebar.collapsed";
const COLLAPSE_EVENT = "docusense:sidebar-preference";
const SESSION_EXPIRED_EVENT = "docusense:session-expired";

function subscribeToCollapsePreference(onChange: () => void) {
  window.addEventListener("storage", onChange);
  window.addEventListener(COLLAPSE_EVENT, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(COLLAPSE_EVENT, onChange);
  };
}

function readCollapsePreference() {
  return window.localStorage.getItem(COLLAPSE_KEY) === "true";
}

export function AppShell({
  profile,
  breadcrumbs,
  notificationCount,
  onLogout,
  children,
}: {
  profile: SessionProfile;
  breadcrumbs?: BreadcrumbItem[];
  notificationCount?: number | null;
  onLogout?: () => void;
  children: ReactNode;
}) {
  const collapsed = useSyncExternalStore(subscribeToCollapsePreference, readCollapsePreference, () => false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [logoutPending, setLogoutPending] = useState(false);
  const shellRef = useRef<HTMLDivElement>(null);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const router = useRouter();
  const pathname = usePathname();
  const items = navigationForRole(profile.role);
  const resolvedBreadcrumbs = breadcrumbs ?? breadcrumbsForPathname(pathname);

  useEffect(() => {
    shellRef.current?.setAttribute("data-hydrated", "true");
  }, []);

  useEffect(() => {
    function redirectExpiredSession(event: Event) {
      const returnTo = event instanceof CustomEvent && typeof event.detail?.returnTo === "string"
        ? event.detail.returnTo
        : "/dashboard";
      router.replace(`/login?reason=session-expired&returnTo=${encodeURIComponent(returnTo)}`);
    }
    window.addEventListener(SESSION_EXPIRED_EVENT, redirectExpiredSession);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, redirectExpiredSession);
  }, [router]);

  function changeCollapsed(next: boolean) {
    window.localStorage.setItem(COLLAPSE_KEY, String(next));
    window.dispatchEvent(new Event(COLLAPSE_EVENT));
  }

  async function handleLogout() {
    if (logoutPending) return;
    if (onLogout) {
      onLogout();
      return;
    }

    setLogoutPending(true);
    try {
      await fetch("/api/session/logout", {
        method: "POST",
        cache: "no-store",
        credentials: "same-origin",
      });
    } finally {
      router.replace("/login?signedOut=1");
      router.refresh();
    }
  }

  return (
    <div ref={shellRef} className="ds-app-shell" data-collapsed={collapsed} data-hydrated="false">
      <SkipLink />
      <GlobalSidebar items={items} collapsed={collapsed} onCollapsedChange={changeCollapsed} />
      <TopContextBar
        breadcrumbs={resolvedBreadcrumbs}
        profile={profile}
        notificationCount={notificationCount}
        onOpenNavigation={() => setMobileOpen(true)}
        menuButtonRef={menuButtonRef}
        onLogout={handleLogout}
        logoutPending={logoutPending}
      />
      <main className="ds-route-main" id="main-content" tabIndex={-1}>
        <div className="ds-route-content">{children}</div>
      </main>
      <MobileNavigationDrawer
        open={mobileOpen}
        items={items}
        onClose={() => setMobileOpen(false)}
        returnFocusRef={menuButtonRef}
      />
    </div>
  );
}

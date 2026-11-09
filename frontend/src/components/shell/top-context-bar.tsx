"use client";

import { Bell, ChevronDown, Menu, UserCircle2 } from "lucide-react";
import type { Route } from "next";
import Link from "next/link";
import { useState, type RefObject } from "react";

import { Badge } from "@/components/ui/feedback";
import { IconButton } from "@/components/ui/button";
import type { SessionProfile } from "@/lib/auth/session-types";

export interface BreadcrumbItem {
  label: string;
  href?: string;
}

export function TopContextBar({
  breadcrumbs,
  profile,
  notificationCount,
  onOpenNavigation,
  menuButtonRef,
  onLogout,
  logoutPending = false,
}: {
  breadcrumbs: BreadcrumbItem[];
  profile: SessionProfile;
  notificationCount?: number | null;
  onOpenNavigation: () => void;
  menuButtonRef: RefObject<HTMLButtonElement | null>;
  onLogout?: () => void;
  logoutPending?: boolean;
}) {
  const [accountOpen, setAccountOpen] = useState(false);

  return (
    <header className="ds-topbar">
      <div className="ds-topbar-start">
        <IconButton
          ref={menuButtonRef}
          className="ds-mobile-menu"
          variant="subtle"
          label="Open navigation"
          icon={<Menu aria-hidden="true" size={20} />}
          onClick={onOpenNavigation}
        />
        <nav className="ds-breadcrumbs" aria-label="Breadcrumb">
          <ol>
            {breadcrumbs.map((item, index) => (
              <li key={`${item.label}-${index}`}>
                {item.href ? <Link href={item.href as Route}>{item.label}</Link> : <span aria-current="page">{item.label}</span>}
              </li>
            ))}
          </ol>
        </nav>
      </div>
      <div className="ds-topbar-end">
        <span className="ds-org-summary" title={profile.organizationName}>
          <span className="ds-topbar-muted">Workspace</span>
          <strong className="ds-topbar-label">{profile.organizationName}</strong>
        </span>
        {typeof notificationCount === "number" ? (
          <>
            <IconButton
              variant="subtle"
              label={notificationCount ? `${notificationCount} notifications` : "Notifications"}
              icon={<Bell aria-hidden="true" size={18} />}
            />
            {notificationCount > 0 ? <Badge tone="technical">{notificationCount}</Badge> : null}
          </>
        ) : null}
        <div className="ds-account-menu">
          <button
            className="ds-account-trigger"
            type="button"
            aria-label={"Account menu for " + profile.displayName}
            aria-expanded={accountOpen}
            aria-controls="docusense-account-popover"
            onClick={() => setAccountOpen((open) => !open)}
          >
            <UserCircle2 aria-hidden="true" size={22} />
            <span className="ds-account-summary">
              <span className="ds-topbar-label">{profile.displayName}</span>
              <ChevronDown aria-hidden="true" size={15} />
            </span>
          </button>
          {accountOpen ? (
            <div className="ds-account-popover" id="docusense-account-popover">
              <strong>{profile.displayName}</strong>
              <span className="ds-topbar-muted">{profile.email}</span>
              <span className="ds-topbar-muted">Role: {profile.role}</span>
              {onLogout ? (
                <button
                  className="ds-button"
                  data-variant="subtle"
                  type="button"
                  disabled={logoutPending}
                  aria-busy={logoutPending || undefined}
                  onClick={onLogout}
                >
                  {logoutPending ? "Signing out…" : "Sign out"}
                </button>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>
    </header>
  );
}

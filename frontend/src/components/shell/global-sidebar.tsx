"use client";

import type { Route } from "next";
import {
  FileStack,
  Gauge,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  Settings,
  Upload,
  X,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { RefObject } from "react";

import { IconButton } from "@/components/ui/button";
import { Drawer } from "@/components/ui/overlays";

import type { NavigationIcon, NavigationItem } from "./navigation";
import { Wordmark } from "./wordmark";

const icons: Record<NavigationIcon, LucideIcon> = {
  dashboard: Gauge,
  documents: FileStack,
  upload: Upload,
  search: Search,
  settings: Settings,
};

function isCurrent(pathname: string, href: string) {
  if (href === "/documents") return pathname === href || /^\/documents\/[0-9a-f-]{36}(?:\/chunks)?$/i.test(pathname);
  return pathname === href || pathname.startsWith(`${href}/`);
}

function NavigationLinks({ items, onNavigate }: { items: NavigationItem[]; onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <nav className="ds-nav" aria-label="Primary navigation">
      {items.map((item) => {
        const Icon = icons[item.icon];
        return (
          <Link
            key={item.href}
            className="ds-nav-link"
            href={item.href as Route}
            aria-current={isCurrent(pathname, item.href) ? "page" : undefined}
            title={item.label}
            onClick={onNavigate}
          >
            <span className="ds-nav-icon"><Icon aria-hidden="true" size={20} strokeWidth={1.75} /></span>
            <span className="ds-nav-copy">
              <span className="ds-nav-label">{item.label}</span>
              {item.meta ? <span className="ds-nav-meta">{item.meta}</span> : null}
            </span>
          </Link>
        );
      })}
    </nav>
  );
}

export function GlobalSidebar({
  items,
  collapsed,
  onCollapsedChange,
}: {
  items: NavigationItem[];
  collapsed: boolean;
  onCollapsedChange: (collapsed: boolean) => void;
}) {
  return (
    <aside className="ds-sidebar" data-collapsed={collapsed} aria-label="Application sidebar">
      <div className="ds-sidebar-head">
        <Wordmark href="/dashboard" />
      </div>
      <NavigationLinks items={items} />
      <div className="ds-sidebar-foot">
        <IconButton
          variant="subtle"
          label={collapsed ? "Expand navigation" : "Collapse navigation"}
          icon={collapsed ? <PanelLeftOpen aria-hidden="true" size={18} /> : <PanelLeftClose aria-hidden="true" size={18} />}
          onClick={() => onCollapsedChange(!collapsed)}
        />
      </div>
    </aside>
  );
}

export function MobileNavigationDrawer({
  open,
  items,
  onClose,
  returnFocusRef,
}: {
  open: boolean;
  items: NavigationItem[];
  onClose: () => void;
  returnFocusRef: RefObject<HTMLElement | null>;
}) {
  return (
    <Drawer
      open={open}
      title="Navigation"
      placement="left"
      onClose={onClose}
      returnFocusRef={returnFocusRef}
      className="ds-drawer"
    >
      <NavigationLinks items={items} onNavigate={onClose} />
      <IconButton
        label="Close navigation"
        icon={<X aria-hidden="true" size={18} />}
        variant="subtle"
        onClick={onClose}
      />
    </Drawer>
  );
}

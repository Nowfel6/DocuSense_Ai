import type { UserRole } from "@/lib/auth/session-types";

export type NavigationIcon = "dashboard" | "documents" | "upload" | "search" | "settings";

export interface NavigationItem {
  href: "/dashboard" | "/documents" | "/documents/upload" | "/documents/search" | "/settings/api";
  label: string;
  icon: NavigationIcon;
  meta?: string;
  roles?: UserRole[];
  available: boolean;
}

export const navigationItems: NavigationItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: "dashboard", available: true },
  { href: "/documents", label: "All documents", icon: "documents", available: true },
  { href: "/documents/upload", label: "Upload", icon: "upload", roles: ["admin", "operator"], available: true },
  { href: "/documents/search", label: "Search & export", icon: "search", available: true },
  { href: "/settings/api", label: "API & integrations", icon: "settings", roles: ["admin"], available: true },
];

export function navigationForRole(role: UserRole): NavigationItem[] {
  return navigationItems.filter((item) => item.available && (!item.roles || item.roles.includes(role)));
}

export function breadcrumbsForPathname(pathname: string) {
  if (pathname === "/settings/api") return [{ label: "Settings" }, { label: "API & Integrations" }];
  if (pathname === "/documents/search") return [{ label: "Documents", href: "/documents" }, { label: "Search & export" }];
  if (pathname === "/documents/upload") return [{ label: "Documents", href: "/documents" }, { label: "Upload" }];
  if (pathname === "/documents") return [{ label: "Documents" }];
  const detail = pathname.match(/^\/documents\/([0-9a-f-]{36})$/i);
  if (detail) return [{ label: "Documents", href: "/documents" }, { label: "Document" }];
  const workbench = pathname.match(/^\/documents\/([0-9a-f-]{36})\/chunks$/i);
  if (workbench) return [
    { label: "Documents", href: "/documents" },
    { label: "Document", href: `/documents/${workbench[1]}` },
    { label: "Chunks & evidence" },
  ];
  const review = pathname.match(/^\/documents\/([0-9a-f-]{36})\/review$/i);
  if (review) return [
    { label: "Documents", href: "/documents" },
    { label: "Document", href: `/documents/${review[1]}` },
    { label: "Review" },
  ];
  return [{ label: "Dashboard" }];
}

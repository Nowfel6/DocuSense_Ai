import type { ReactNode } from "react";

import { PublicShell } from "@/components/shell/public-shell";

export default function LoginLayout({ children }: Readonly<{ children: ReactNode }>) {
  return <PublicShell>{children}</PublicShell>;
}

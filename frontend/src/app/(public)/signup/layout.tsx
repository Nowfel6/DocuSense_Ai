import type { ReactNode } from "react";

import { PublicShell } from "@/components/shell/public-shell";

export default function SignupLayout({ children }: Readonly<{ children: ReactNode }>) {
  return <PublicShell>{children}</PublicShell>;
}

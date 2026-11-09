import type { Metadata } from "next";
import type { ReactNode } from "react";

import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "DocuSense",
    template: "%s · DocuSense",
  },
  description: "Traceable document processing, retrieval, and human review.",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    // Browser extensions (e.g. Bitwarden) inject attributes such as `bis_skin_checked`
    // into the served HTML before React hydrates. suppressHydrationWarning tells React
    // to accept the DOM for these top-level wrappers instead of reporting mismatches.
    <html lang="en" suppressHydrationWarning>
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}

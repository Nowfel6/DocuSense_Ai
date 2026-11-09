import type { Metadata } from "next";

import "../../../src/app/globals.css";

export const metadata: Metadata = {
  title: "DocuSense foundation test fixture",
};

export default function TestFixtureLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}

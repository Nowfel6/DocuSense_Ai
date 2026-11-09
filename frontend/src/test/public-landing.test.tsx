import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LandingShell } from "@/features/public-landing/landing-shell";
import { PublicLandingView } from "@/features/public-landing/public-landing-view";

describe("public landing", () => {
  it("renders the approved hierarchy and traceable workflow", () => {
    render(<LandingShell><PublicLandingView /></LandingShell>);

    expect(screen.getByRole("heading", {
      level: 1,
      name: "Turn complex documents into evidence-backed decisions.",
    })).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 2 })).toHaveLength(4);

    const workflow = screen.getByRole("heading", {
      name: "One traceable path from upload to review.",
    }).closest("section");
    expect(workflow).not.toBeNull();
    const steps = within(workflow as HTMLElement).getAllByRole("listitem");
    expect(steps).toHaveLength(6);
    expect(steps.map((step) => step.querySelector("h3")?.textContent)).toEqual([
      "Upload", "Parse", "Chunk", "Retrieve and extract", "Validate", "Review",
    ]);
  });

  it("offers only real same-origin sign-in navigation and makes no request", () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<LandingShell><PublicLandingView /></LandingShell>);

    expect(screen.getByRole("link", { name: "DocuSense home" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/login");
    expect(screen.getByRole("link", { name: "Sign in to DocuSense" })).toHaveAttribute("href", "/login");
    expect(screen.getByRole("link", { name: "Continue to sign in" })).toHaveAttribute("href", "/login");
    expect(screen.queryByRole("link", { name: /sign up|pricing|demo|contact/i })).not.toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("provides one main landmark, a working skip target, and no customer data", () => {
    render(<LandingShell><PublicLandingView /></LandingShell>);

    expect(screen.getByRole("main")).toHaveAttribute("id", "main-content");
    expect(screen.getByRole("link", { name: "Skip to main content" })).toHaveAttribute("href", "#main-content");
    expect(screen.getByRole("contentinfo")).toHaveTextContent(
      "DocuSense · Traceable document processing and human review.",
    );
    expect(document.body).not.toHaveTextContent(/invoice number|acme|request id|api key|webhook/i);
  });
});

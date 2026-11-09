import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Alert, RouteState, StatusBadge } from "@/components/ui";

describe("foundation feedback", () => {
  it("renders backend status with text rather than color alone", () => {
    render(<StatusBadge status="pending_review" />);
    expect(screen.getByText("Pending review")).toBeInTheDocument();
  });

  it("keeps safe error information persistent", () => {
    render(<Alert tone="error" title="Upload failed" message="Try the upload again." />);
    expect(screen.getByRole("alert")).toHaveTextContent("Upload failed");
  });

  it("shows a support request id without raw failure details", () => {
    render(<RouteState kind="error" title="Could not load" message="Try again." requestId="req_fixture_12" />);
    expect(screen.getByText("Request ID: req_fixture_12")).toBeInTheDocument();
  });
});

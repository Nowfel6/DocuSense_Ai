"use client";

import { useRef, useState } from "react";

import { AppShell } from "@/components/shell";
import {
  Alert,
  Badge,
  Button,
  Checkbox,
  Dialog,
  EmptyState,
  PageHeader,
  Pagination,
  SelectField,
  Skeleton,
  StatusBadge,
  TableFrame,
  Tabs,
  TextField,
  ToastRegion,
} from "@/components/ui";
import { allFoundationStatuses, fixtureMetadata, operatorProfile } from "@/test/fixtures/foundation-shell";

export function FoundationPreview() {
  const [dialogOpen, setDialogOpen] = useState(false);
  const [selectedTab, setSelectedTab] = useState("components");
  const [page, setPage] = useState(1);
  const dialogTrigger = useRef<HTMLButtonElement>(null);

  return (
    <AppShell
      profile={operatorProfile}
      breadcrumbs={[{ label: "Foundation" }, { label: "Component preview" }]}
      notificationCount={3}
      onLogout={() => undefined}
    >
      <PageHeader
        title="Frontend foundation"
        description={`${fixtureMetadata.apiMode}: a synthetic Stage 3 harness for shell and component verification.`}
        actions={<Button ref={dialogTrigger} variant="primary" onClick={() => setDialogOpen(true)}>Open dialog</Button>}
      />

      <Tabs
        label="Foundation preview sections"
        selectedId={selectedTab}
        onSelect={setSelectedTab}
        items={[
          {
            id: "components",
            label: "Components",
            panel: (
              <div className="ds-preview-grid">
                <section className="ds-surface ds-preview-panel ds-stack" aria-labelledby="preview-actions">
                  <h2 id="preview-actions">Actions and fields</h2>
                  <div className="ds-row">
                    <Button variant="primary">Primary action</Button>
                    <Button>Secondary action</Button>
                    <Button variant="subtle">Subtle action</Button>
                    <Button variant="destructive">Destructive</Button>
                    <Button isPending>Save changes</Button>
                  </div>
                  <TextField label="Document name" helpText="Use a clear internal title." placeholder="Quarterly invoices" />
                  <TextField label="Reference" error="The reference is required." aria-invalid="true" />
                  <SelectField label="Processing priority" defaultValue="normal">
                    <option value="normal">Normal</option>
                    <option value="high">High</option>
                  </SelectField>
                  <Checkbox label="Include table extraction" defaultChecked />
                </section>

                <section className="ds-surface ds-preview-panel ds-stack" aria-labelledby="preview-statuses">
                  <h2 id="preview-statuses">Statuses and feedback</h2>
                  <div className="ds-row">
                    {allFoundationStatuses.map((status) => <StatusBadge key={status} status={status} />)}
                  </div>
                  <div className="ds-row">
                    <Badge>Neutral</Badge><Badge tone="technical">Technical</Badge><Badge tone="warning">Warning</Badge>
                  </div>
                  <Alert tone="success" title="Changes saved" message="The server confirmed the update." />
                  <Alert tone="error" title="Network request failed" message="Try again when the service is available." />
                  <Skeleton shape="row" />
                </section>

                <section className="ds-surface ds-preview-panel ds-stack" aria-labelledby="preview-table">
                  <h2 id="preview-table">Table and pagination</h2>
                  <TableFrame caption="Synthetic document status examples" headers={["Document", "Status"]}>
                    <tr><td>Invoice sample.pdf</td><td><StatusBadge status="processing" /></td></tr>
                    <tr><td>Freight summary.pdf</td><td><StatusBadge status="pending_review" /></td></tr>
                  </TableFrame>
                  <Pagination
                    page={page}
                    totalPages={3}
                    onFirst={() => setPage(1)}
                    onPrevious={() => setPage((value) => Math.max(1, value - 1))}
                    onNext={() => setPage((value) => Math.min(3, value + 1))}
                    onLast={() => setPage(3)}
                  />
                </section>

                <EmptyState title="No matching documents" message="Change the filters or upload the first document." action={<Button>Clear filters</Button>} />
              </div>
            ),
          },
          {
            id: "states",
            label: "Route states",
            panel: <Alert title="Fixture-only route" message="No backend calls are made by this preview." />,
          },
          { id: "disabled", label: "Unavailable", panel: null, disabled: true },
        ]}
      />

      <Dialog
        open={dialogOpen}
        title="Confirm foundation action"
        description="This fixture action does not change production data."
        confirmLabel="Confirm"
        onConfirm={() => setDialogOpen(false)}
        onClose={() => setDialogOpen(false)}
        returnFocusRef={dialogTrigger}
      />
      <ToastRegion items={[{ id: "fixture-toast", title: "Design fixture active", message: "Live API integration is not claimed." }]} />
    </AppShell>
  );
}

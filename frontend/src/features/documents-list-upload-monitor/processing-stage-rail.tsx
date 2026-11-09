import { Check, Circle, CircleAlert, LoaderCircle } from "lucide-react";

import type { ProcessingStage, StageStatus } from "./types";
import styles from "./documents-list-upload-monitor.module.css";

const STAGES: ReadonlyArray<{ key: ProcessingStage; label: string }> = [
  { key: "upload", label: "Upload" },
  { key: "partitioning", label: "Partitioning" },
  { key: "chunking", label: "Chunking" },
  { key: "vectorizing", label: "Vectorizing" },
  { key: "extracting", label: "Extraction & validation" },
];

const STATE_LABEL: Record<StageStatus, string> = {
  pending: "Pending",
  in_progress: "In progress",
  completed: "Completed",
  failed: "Failed",
};

function StageIcon({ status }: { status: StageStatus }) {
  if (status === "completed") return <Check aria-hidden="true" size={18} />;
  if (status === "in_progress") return <LoaderCircle aria-hidden="true" size={18} />;
  if (status === "failed") return <CircleAlert aria-hidden="true" size={18} />;
  return <Circle aria-hidden="true" size={18} />;
}

export function ProcessingStageRail({ stages }: { stages: Record<ProcessingStage, StageStatus> }) {
  return (
    <ol className={styles.stageRail} aria-label="Document processing stages">
      {STAGES.map((stage) => {
        const status = stages[stage.key];
        return (
          <li key={stage.key} data-status={status} aria-current={status === "in_progress" ? "step" : undefined}>
            <span className={styles.stageIcon}><StageIcon status={status} /></span>
            <span><strong>{stage.label}</strong><small>{STATE_LABEL[status]}</small></span>
          </li>
        );
      })}
    </ol>
  );
}

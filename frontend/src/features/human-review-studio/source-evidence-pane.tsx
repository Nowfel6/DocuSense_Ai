import { Badge } from "@/components/ui/feedback";
import { SourceViewAction } from "@/features/document-detail-chunk-inspector/source-view-action";
import type { DocumentDetail } from "@/features/document-detail-chunk-inspector/types";

import styles from "./human-review-studio.module.css";

export function SourceEvidencePane({
  detail,
  sourceBlocked,
  sourceRefreshing,
  onRefreshSource,
}: {
  detail: DocumentDetail;
  sourceBlocked: boolean;
  sourceRefreshing: boolean;
  onRefreshSource: () => void;
}) {
  const evidence = [...detail.field_evidence].sort((a, b) => {
    const priority = { invalid: 0, missing: 1, ambiguous: 2, unsupported: 3, valid: 4 };
    return priority[a.validation_state] - priority[b.validation_state];
  });
  return (
    <section className={styles.sourcePane} aria-labelledby="source-evidence-heading">
      <div className={styles.sectionHeading}>
        <div>
          <h2 id="source-evidence-heading">Evidence & source</h2>
          <p>The original source opens separately in a short-lived secure view.</p>
        </div>
      </div>
      <SourceViewAction source={detail.source_view} blocked={sourceBlocked} refreshing={sourceRefreshing} onRefresh={onRefreshSource} />
      <div className={styles.evidenceList}>
        {evidence.length === 0 ? <p className={styles.emptyText}>No field evidence was returned for this extraction.</p> : null}
        {evidence.map((item) => (
          <article key={item.field_path} className={styles.evidenceCard}>
            <div className={styles.evidenceHeading}>
              <strong>{item.field_path}</strong>
              <Badge tone={item.validation_state === "valid" ? "success" : item.validation_state === "invalid" ? "danger" : "warning"}>{item.validation_state}</Badge>
            </div>
            <p>{item.evidence_excerpt ?? "No source excerpt is available."}</p>
            <dl>
              <div><dt>Source page</dt><dd>{item.source_page ?? "Unavailable"}</dd></div>
              <div><dt>Extraction confidence</dt><dd>{item.confidence_score.toFixed(1)}%</dd></div>
            </dl>
            {item.source_page ? <SourceViewAction source={detail.source_view} page={item.source_page} blocked={sourceBlocked} refreshing={sourceRefreshing} onRefresh={onRefreshSource} compact /> : null}
          </article>
        ))}
      </div>
    </section>
  );
}

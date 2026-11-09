import {
  FileSearch,
  History,
  ListChecks,
  LockKeyhole,
  PanelsTopLeft,
  ScanSearch,
  ShieldCheck,
  UserRoundCheck,
} from "lucide-react";
import type { Route } from "next";
import Link from "next/link";

import styles from "./public-landing.module.css";

const outcomes = [
  {
    title: "Preserve document structure",
    description: "Layout-aware processing keeps sections, tables, and source context connected.",
    icon: PanelsTopLeft,
  },
  {
    title: "Ground extraction in evidence",
    description: "Retrieved source passages make extracted fields and review decisions easier to inspect.",
    icon: ScanSearch,
  },
  {
    title: "Validate deterministic rules",
    description: "Business and arithmetic checks stay separate from AI-assisted extraction.",
    icon: ListChecks,
  },
  {
    title: "Keep people in control",
    description: "Human review, corrections, decisions, and audit history remain part of the governed workflow.",
    icon: UserRoundCheck,
  },
] as const;

const workflow = [
  ["Upload", "Accept a document into a tenant-aware workflow."],
  ["Parse", "Recover layout, text, and table structure."],
  ["Chunk", "Organize source material into retrievable evidence."],
  ["Retrieve and extract", "Use relevant evidence to produce structured fields."],
  ["Validate", "Apply deterministic checks independently from extraction."],
  ["Review", "Inspect evidence, correct fields, and record the final decision."],
] as const;

const trust = [
  {
    title: "Tenant-aware access",
    description: "Authenticated workflows enforce role and tenant boundaries.",
    icon: ShieldCheck,
  },
  {
    title: "Private document handling",
    description: "Documents and generated artifacts remain behind authorized application flows.",
    icon: LockKeyhole,
  },
  {
    title: "Evidence-linked review",
    description: "Reviewers can trace extracted information back to its source context.",
    icon: FileSearch,
  },
  {
    title: "Auditable decisions",
    description: "Corrections and review outcomes remain visible as part of the document history.",
    icon: History,
  },
] as const;

export function PublicLandingView() {
  return (
    <>
      <section className={`${styles.section} ${styles.hero}`} aria-labelledby="landing-title">
        <div className={styles.heroCopy}>
          <p className={styles.eyebrow}>Traceable document intelligence</p>
          <h1 id="landing-title">Turn complex documents into evidence-backed decisions.</h1>
          <p className={styles.heroLead}>
            DocuSense preserves document structure, retrieves the evidence behind each extraction,
            applies deterministic validation, and keeps people in control of final review.
          </p>
          <div className={styles.heroActions}>
            <Link className="ds-button" data-variant="primary" href="/login">
              Sign in to DocuSense
            </Link>
            <Link className="ds-button" data-variant="secondary" href={"/signup" as Route}>
              Create account
            </Link>
          </div>
          <p className={styles.supportingNote}>
            Built for governed document workflows—not black-box output.
          </p>
        </div>
        <div className={styles.evidencePath} aria-label="Traceable processing path">
          <p className={styles.evidenceLabel}>Evidence stays connected</p>
          <ol>
            {workflow.map(([title]) => <li key={title}>{title}</li>)}
          </ol>
          <p>Source context remains available from ingestion through human review.</p>
        </div>
      </section>

      <section className={`${styles.section} ${styles.splitSection}`} aria-labelledby="outcome-title">
        <div className={styles.sectionIntro}>
          <p className={styles.eyebrow}>Why DocuSense</p>
          <h2 id="outcome-title">Structure, evidence, and review stay connected.</h2>
          <p>
            Dense invoices and supply-chain documents contain tables, totals, and context that flat
            text extraction can lose. DocuSense keeps those relationships inspectable from processing
            through approval.
          </p>
        </div>
        <ul className={styles.cardGrid}>
          {outcomes.map(({ title, description, icon: Icon }) => (
            <li className={styles.card} key={title}>
              <Icon aria-hidden="true" size={22} strokeWidth={1.7} />
              <h3>{title}</h3>
              <p>{description}</p>
            </li>
          ))}
        </ul>
      </section>

      <section className={`${styles.section} ${styles.workflowSection}`} aria-labelledby="workflow-title">
        <div className={styles.sectionIntroWide}>
          <p className={styles.eyebrow}>How it works</p>
          <h2 id="workflow-title">One traceable path from upload to review.</h2>
          <p>
            Each stage preserves the context needed by the next, while the application exposes
            progress and evidence instead of hiding the pipeline.
          </p>
        </div>
        <ol className={styles.workflowList}>
          {workflow.map(([title, description], index) => (
            <li key={title}>
              <span aria-hidden="true">{String(index + 1).padStart(2, "0")}</span>
              <h3>{title}</h3>
              <p>{description}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className={`${styles.section} ${styles.splitSection}`} aria-labelledby="trust-title">
        <div className={styles.sectionIntro}>
          <p className={styles.eyebrow}>Designed for oversight</p>
          <h2 id="trust-title">Operational transparency is part of the product.</h2>
          <p>
            DocuSense keeps authorization, document handling, validation decisions, and review
            history inside governed application boundaries.
          </p>
        </div>
        <ul className={styles.trustList}>
          {trust.map(({ title, description, icon: Icon }) => (
            <li key={title}>
              <Icon aria-hidden="true" size={20} strokeWidth={1.7} />
              <div>
                <h3>{title}</h3>
                <p>{description}</p>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <section className={`${styles.section} ${styles.finalCta}`} aria-labelledby="final-cta-title">
        <div>
          <h2 id="final-cta-title">Bring traceability to every document decision.</h2>
          <p>
            Continue to the secure DocuSense workspace to process, inspect, review, search, and
            export authorized documents.
          </p>
        </div>
        <div className={styles.finalCtaActions}>
          <Link className="ds-button" data-variant="primary" href="/login">
            Continue to sign in
          </Link>
          <Link className="ds-button" data-variant="secondary" href={"/signup" as Route}>
            Create account
          </Link>
        </div>
      </section>
    </>
  );
}

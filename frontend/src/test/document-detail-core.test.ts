import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import {
  validateChunkListEnvelope,
  validateDocumentDetailEnvelope,
  validateEvidenceResponse,
} from "@/features/document-detail-chunk-inspector/api";
import { sourceHref, sourceIsExpired } from "@/features/document-detail-chunk-inspector/source-view";
import { backendWorkbenchQuery, normalizeWorkbenchQuery } from "@/features/document-detail-chunk-inspector/workbench-query";
import { safeReturnPath } from "@/lib/auth/return-path";

import { chunkListFixture, documentDetailFixture, evidenceFixture } from "./fixtures/document-detail-chunk-inspector";
import { fixtureDocumentId } from "./fixtures/documents-list-upload-monitor";

describe("document detail contract boundary", () => {
  it("accepts the three canonical response shapes", () => {
    expect(validateDocumentDetailEnvelope(structuredClone(documentDetailFixture)).data.document_id).toBe(fixtureDocumentId);
    expect(validateChunkListEnvelope(structuredClone(chunkListFixture)).data[0].has_embedding).toBe(true);
    expect(validateEvidenceResponse(structuredClone(evidenceFixture)).data.items[0].field_path).toBe("invoice.grand_total");
  });

  it("rejects unsafe source URLs and inconsistent embedding state", () => {
    const unsafe = structuredClone(documentDetailFixture);
    unsafe.data.source_view.url = "http://objects.example.invalid/document.pdf";
    expect(() => validateDocumentDetailEnvelope(unsafe)).toThrow(/unexpected response/i);

    const inconsistent = structuredClone(chunkListFixture);
    inconsistent.data[0].has_embedding = false;
    expect(() => validateChunkListEnvelope(inconsistent)).toThrow(/unexpected response/i);
  });
});

describe("workbench URL and source safety", () => {
  it("canonicalizes exact, mode-aware filters and backend parameters", () => {
    const normalized = normalizeWorkbenchQuery("mode=evidence&field_path=invoice.grand_total&chunk_type=text&page=2&page_size=20&unknown=x");
    expect(normalized.reset).toBe(true);
    expect(normalized.canonical).toBe("mode=evidence&page=2&page_size=20&field_path=invoice.grand_total");
    expect(backendWorkbenchQuery(normalized.query)).toBe("page=2&page_size=20&field_path=invoice.grand_total");
  });

  it("sanitizes nested return paths with the same canonical query", () => {
    const candidate = `/documents/${fixtureDocumentId}/chunks?mode=evidence&field_path=invoice.grand_total&secret=x`;
    expect(safeReturnPath(candidate)).toBe(`/documents/${fixtureDocumentId}/chunks?mode=evidence&field_path=invoice.grand_total`);
    expect(safeReturnPath(`/documents/${fixtureDocumentId}?secret=x`)).toBe(`/documents/${fixtureDocumentId}`);
  });

  it("adds a PDF page fragment only while the HTTPS source is usable", () => {
    const source = documentDetailFixture.data.source_view;
    expect(sourceHref(source, 2)).toContain("#page=2");
    expect(sourceIsExpired(source, Date.parse("2030-09-15T08:09:31Z"))).toBe(true);
  });
});

describe("checked-in API contract", () => {
  it("contains the four feature endpoints in the generated artifact", () => {
    const candidates = [
      resolve(process.cwd(), "../../../../final_project/docs/api/openapi.yaml"),
      resolve(process.cwd(), "../docs/api/openapi.yaml"),
    ];
    const contractPath = candidates.find(existsSync);
    expect(contractPath).toBeDefined();
    const contract = JSON.parse(readFileSync(contractPath!, "utf8")) as { paths: Record<string, unknown> };
    expect(Object.keys(contract.paths)).toEqual(expect.arrayContaining([
      "/api/v1/documents/{document_id}",
      "/api/v1/documents/{document_id}/status",
      "/api/v1/documents/{document_id}/chunks",
      "/api/v1/documents/{document_id}/extraction-evidence",
    ]));
  });
});

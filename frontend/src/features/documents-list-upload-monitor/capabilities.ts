import type { DocumentType } from "./types";

export const MAX_DOCUMENT_BYTES = 10_485_760;

export const DOCUMENT_TYPE_OPTIONS: ReadonlyArray<{ value: DocumentType; label: string }> = [
  { value: "commercial_invoice", label: "Commercial invoice" },
  { value: "purchase_order", label: "Purchase order" },
  { value: "packing_list", label: "Packing list" },
];

const EXTENSION_MIME: Record<string, ReadonlySet<string>> = {
  ".pdf": new Set(["application/pdf", "", "application/octet-stream"]),
  ".png": new Set(["image/png", "", "application/octet-stream"]),
  ".jpg": new Set(["image/jpeg", "", "application/octet-stream"]),
  ".jpeg": new Set(["image/jpeg", "", "application/octet-stream"]),
};

export function validateDocumentFile(file: File | null): string | null {
  if (!file) return "Choose a document to upload.";
  if (file.size === 0) return "Choose a file that is not empty.";
  if (file.size > MAX_DOCUMENT_BYTES) return "Choose a file no larger than 10 MiB.";
  if (/[\\/\u0000-\u001f\u007f]/.test(file.name)) return "Choose a file with a safe file name.";

  const extension = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
  const allowedMime = EXTENSION_MIME[extension];
  if (!allowedMime) return "Choose a PDF, PNG, JPG, or JPEG file.";
  if (!allowedMime.has(file.type)) return "The file extension and browser file type do not match.";
  return null;
}

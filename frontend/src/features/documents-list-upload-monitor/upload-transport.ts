import { apiErrorFromPayload } from "@/lib/api/client";
import { ApiError, normalizeApiError } from "@/lib/api/errors";

import { validateUploadEnvelope } from "./api";
import type { DocumentType, UploadAccepted } from "./types";

export type UploadProgress =
  | { phase: "transferring"; percentage?: number }
  | { phase: "accepting"; percentage: 100 };

export interface UploadDocumentOptions {
  file: File;
  documentType: DocumentType;
  confirmDuplicate: boolean;
  signal?: AbortSignal;
  onProgress?: (progress: UploadProgress) => void;
}

export function uploadDocument(options: UploadDocumentOptions): Promise<UploadAccepted> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const body = new FormData();
    body.set("file", options.file);
    body.set("doc_type_hint", options.documentType);
    body.set("confirm_duplicate", String(options.confirmDuplicate));

    const abort = () => xhr.abort();
    const finish = () => options.signal?.removeEventListener("abort", abort);
    options.signal?.addEventListener("abort", abort, { once: true });

    xhr.open("POST", "/api/backend/api/v1/documents/upload");
    xhr.withCredentials = true;
    xhr.timeout = 120_000;
    xhr.setRequestHeader("accept", "application/json");

    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable || event.total <= 0) {
        options.onProgress?.({ phase: "transferring" });
        return;
      }
      const percentage = Math.min(100, Math.round((event.loaded / event.total) * 100));
      options.onProgress?.(percentage >= 100
        ? { phase: "accepting", percentage: 100 }
        : { phase: "transferring", percentage });
    };

    xhr.onload = () => {
      finish();
      let payload: unknown = null;
      try { payload = JSON.parse(xhr.responseText); } catch { /* normalized below */ }
      if (xhr.status === 401 && typeof window !== "undefined") {
        window.dispatchEvent(new CustomEvent("docusense:session-expired", {
          detail: { returnTo: window.location.pathname + window.location.search },
        }));
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(validateUploadEnvelope(payload).data);
        } catch (error) {
          reject(normalizeApiError(error));
        }
        return;
      }
      reject(apiErrorFromPayload(payload, xhr.status, { get: (name) => xhr.getResponseHeader(name) }));
    };
    xhr.onerror = () => { finish(); reject(new ApiError("The service could not be reached. Try again.", { code: "NETWORK_ERROR" })); };
    xhr.ontimeout = () => { finish(); reject(new ApiError("The upload timed out. Check Documents before trying again.", { code: "REQUEST_TIMEOUT" })); };
    xhr.onabort = () => { finish(); reject(new ApiError("The request was canceled.", { code: "REQUEST_ABORTED" })); };

    if (options.signal?.aborted) {
      xhr.abort();
      return;
    }
    options.onProgress?.({ phase: "transferring" });
    xhr.send(body);
  });
}

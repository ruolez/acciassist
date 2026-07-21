import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { api, ApiError, apiUpload } from "../../api/client";
import type { CaseDocument } from "../../api/types";
import { formatBytes, relativeTime } from "../../lib/format";

const ACCEPT = ".pdf,.jpg,.jpeg,.png,.webp,.heic,.doc,.docx";
const MAX_MB = 15;

function DocIcon({ contentType }: { contentType: string }) {
  const isImage = contentType.startsWith("image/");
  return (
    <span className={`doc-icon ${isImage ? "image" : "file"}`} aria-hidden="true">
      <svg
        viewBox="0 0 24 24"
        width="18"
        height="18"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {isImage ? (
          <>
            <rect x="3" y="3" width="18" height="18" rx="2" />
            <circle cx="8.5" cy="8.5" r="1.5" />
            <path d="m21 15-5-5L5 21" />
          </>
        ) : (
          <>
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
          </>
        )}
      </svg>
    </span>
  );
}

export function DocumentsSection({ caseId }: { caseId: string }) {
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState<string[]>([]);
  const [errors, setErrors] = useState<string[]>([]);

  const KEY = ["user", "cases", caseId, "documents"];
  const { data: docs } = useQuery({
    queryKey: KEY,
    queryFn: () => api<CaseDocument[]>(`/me/cases/${caseId}/documents`),
  });

  const removeDoc = useMutation({
    mutationFn: (docId: number) =>
      api(`/me/cases/${caseId}/documents/${docId}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: KEY }),
  });

  const uploadFiles = async (files: FileList | File[]) => {
    setErrors([]);
    const list = Array.from(files);
    const problems: string[] = [];
    for (const file of list) {
      if (file.size > MAX_MB * 1024 * 1024) {
        problems.push(`${file.name}: larger than ${MAX_MB} MB.`);
        continue;
      }
      setUploading((u) => [...u, file.name]);
      try {
        await apiUpload<CaseDocument>(`/me/cases/${caseId}/documents`, file);
      } catch (e) {
        problems.push(
          `${file.name}: ${e instanceof ApiError ? e.message : "upload failed."}`,
        );
      } finally {
        setUploading((u) => u.filter((n) => n !== file.name));
      }
    }
    setErrors(problems);
    queryClient.invalidateQueries({ queryKey: KEY });
  };

  return (
    <div className="portal-section">
      <h2>Your documents</h2>
      <p className="portal-section-sub">
        Medical bills, records, photos, and letters all strengthen your case. Upload them
        here and our team sees them right away.
      </p>

      <div
        className={`dropzone card ${dragging ? "dragging" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          if (e.dataTransfer.files.length) uploadFiles(e.dataTransfer.files);
        }}
      >
        <span className="dropzone-icon" aria-hidden="true">
          <svg
            viewBox="0 0 24 24"
            width="26"
            height="26"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.7"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="17 8 12 3 7 8" />
            <line x1="12" y1="3" x2="12" y2="15" />
          </svg>
        </span>
        <p className="dropzone-text">
          Drag files here, or{" "}
          <button
            type="button"
            className="dropzone-browse"
            onClick={() => inputRef.current?.click()}
          >
            browse your device
          </button>
        </p>
        <p className="dropzone-hint">PDF, Word, or photos · up to {MAX_MB} MB each</p>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          multiple
          hidden
          onChange={(e) => {
            if (e.target.files?.length) uploadFiles(e.target.files);
            e.target.value = "";
          }}
        />
      </div>

      {uploading.map((name) => (
        <p key={name} className="doc-uploading">
          <span className="doc-spinner" aria-hidden="true" /> Uploading {name}…
        </p>
      ))}
      {errors.map((msg) => (
        <p key={msg} className="error-text doc-error">
          {msg}
        </p>
      ))}

      {docs && docs.length > 0 && (
        <div className="doc-list">
          {docs.map((d) => (
            <div key={d.id} className="card doc-row">
              <DocIcon contentType={d.content_type} />
              <span className="doc-main">
                <a
                  className="doc-name"
                  href={`/api/me/cases/${caseId}/documents/${d.id}/download`}
                >
                  {d.original_name}
                </a>
                <span className="doc-meta" title={new Date(d.created_at).toLocaleString()}>
                  {formatBytes(d.size_bytes)} · added {relativeTime(d.created_at)}
                </span>
              </span>
              <button
                className="doc-remove"
                aria-label={`Remove ${d.original_name}`}
                disabled={removeDoc.isPending}
                onClick={() => {
                  if (confirm(`Remove ${d.original_name}?`)) removeDoc.mutate(d.id);
                }}
              >
                Remove
              </button>
            </div>
          ))}
        </div>
      )}
      {docs && docs.length === 0 && uploading.length === 0 && (
        <p className="doc-none muted">
          Nothing uploaded yet — even phone photos of bills and paperwork help.
        </p>
      )}
    </div>
  );
}

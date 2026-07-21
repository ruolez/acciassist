import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { api, ApiError, apiUpload } from "../../api/client";
import type { CaseDocument, DocumentType } from "../../api/types";
import { formatBytes, relativeTime } from "../../lib/format";

const ACCEPT = ".pdf,.jpg,.jpeg,.png,.webp,.heic,.doc,.docx";
const MAX_MB = 15;

type StagedFile = {
  key: string;
  file: File;
  label: string;
};

function guessLabel(file: File, types: DocumentType[]): string {
  if (types.length === 0) return "";
  if (file.type.startsWith("image/")) {
    const photo = types.find((t) => t.name.toLowerCase() === "photo");
    if (photo) return photo.name;
  }
  return types[0].name;
}

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
  const [staged, setStaged] = useState<StagedFile[]>([]);
  const [uploading, setUploading] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);

  const KEY = ["user", "cases", caseId, "documents"];
  const { data: docs } = useQuery({
    queryKey: KEY,
    queryFn: () => api<CaseDocument[]>(`/me/cases/${caseId}/documents`),
  });
  const { data: docTypes = [] } = useQuery({
    queryKey: ["user", "document-types"],
    queryFn: () => api<DocumentType[]>("/me/document-types"),
    staleTime: 5 * 60 * 1000,
  });

  const removeDoc = useMutation({
    mutationFn: (docId: number) =>
      api(`/me/cases/${caseId}/documents/${docId}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: KEY }),
  });

  const stageFiles = (files: FileList | File[]) => {
    const problems: string[] = [];
    const accepted: StagedFile[] = [];
    for (const file of Array.from(files)) {
      if (file.size > MAX_MB * 1024 * 1024) {
        problems.push(`${file.name}: larger than ${MAX_MB} MB.`);
        continue;
      }
      accepted.push({
        key: `${file.name}-${file.size}-${file.lastModified}`,
        file,
        label: guessLabel(file, docTypes),
      });
    }
    setErrors(problems);
    setStaged((s) => {
      const existing = new Set(s.map((f) => f.key));
      return [...s, ...accepted.filter((f) => !existing.has(f.key))];
    });
  };

  const setLabel = (key: string, label: string) =>
    setStaged((s) => s.map((f) => (f.key === key ? { ...f, label } : f)));

  const unstage = (key: string) => setStaged((s) => s.filter((f) => f.key !== key));

  const uploadAll = async () => {
    setUploading(true);
    setErrors([]);
    const problems: string[] = [];
    for (const item of staged) {
      try {
        await apiUpload<CaseDocument>(
          `/me/cases/${caseId}/documents`,
          item.file,
          item.label ? { label: item.label } : {},
        );
        unstage(item.key);
      } catch (e) {
        problems.push(
          `${item.file.name}: ${e instanceof ApiError ? e.message : "upload failed."}`,
        );
      }
    }
    setErrors(problems);
    setUploading(false);
    queryClient.invalidateQueries({ queryKey: KEY });
  };

  return (
    <div className="portal-section portal-section-first">
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
          if (e.dataTransfer.files.length) stageFiles(e.dataTransfer.files);
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
            if (e.target.files?.length) stageFiles(e.target.files);
            e.target.value = "";
          }}
        />
      </div>

      {staged.length > 0 && (
        <div className="card staged-card">
          <p className="staged-head">
            Tell us what {staged.length === 1 ? "this file is" : "these files are"} so
            our team can file {staged.length === 1 ? "it" : "them"} correctly:
          </p>
          {staged.map((item) => (
            <div key={item.key} className="staged-row">
              <DocIcon contentType={item.file.type} />
              <span className="doc-main">
                <span className="doc-name">{item.file.name}</span>
                <span className="doc-meta">{formatBytes(item.file.size)}</span>
              </span>
              <select
                className="select staged-select"
                aria-label={`Document type for ${item.file.name}`}
                value={item.label}
                disabled={uploading || docTypes.length === 0}
                onChange={(e) => setLabel(item.key, e.target.value)}
              >
                {docTypes.length === 0 && <option value="">No types configured</option>}
                {docTypes.map((t) => (
                  <option key={t.id} value={t.name}>
                    {t.name}
                  </option>
                ))}
              </select>
              <button
                className="doc-remove"
                disabled={uploading}
                onClick={() => unstage(item.key)}
              >
                Remove
              </button>
            </div>
          ))}
          <div className="staged-actions">
            <button className="btn btn-primary" disabled={uploading} onClick={uploadAll}>
              {uploading ? (
                <>
                  <span className="doc-spinner" aria-hidden="true" /> Uploading…
                </>
              ) : (
                `Upload ${staged.length} file${staged.length === 1 ? "" : "s"}`
              )}
            </button>
            <button
              className="btn btn-ghost"
              disabled={uploading}
              onClick={() => setStaged([])}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

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
              {d.label && <span className="doc-label">{d.label}</span>}
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
      {docs && docs.length === 0 && staged.length === 0 && (
        <p className="doc-none muted">
          Nothing uploaded yet — even phone photos of bills and paperwork help.
        </p>
      )}
    </div>
  );
}

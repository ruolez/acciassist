import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { api } from "../../api/client";
import type { DocumentType } from "../../api/types";
import { SortableList } from "./SortableList";
import { useActionError } from "./useActionError";

const KEY = ["admin", "document-types"];

/** Settings → Documents: the labels patients pick when uploading files. */
export function DocumentTypesCard() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const { error, onError, clear } = useActionError();

  const { data, isLoading } = useQuery({
    queryKey: KEY,
    queryFn: () => api<DocumentType[]>("/admin/document-types"),
  });

  const invalidate = () => {
    clear();
    queryClient.invalidateQueries({ queryKey: KEY });
  };

  const create = useMutation({
    mutationFn: () => api("/admin/document-types", { method: "POST", body: { name } }),
    onSuccess: () => {
      setName("");
      invalidate();
    },
    onError: (e) => onError(e, "Could not add the document type"),
  });

  const remove = useMutation({
    mutationFn: (id: number) => api(`/admin/document-types/${id}`, { method: "DELETE" }),
    onSuccess: invalidate,
    onError: (e) => onError(e, "Could not delete the document type"),
  });

  const reorder = useMutation({
    mutationFn: (orderedIds: number[]) =>
      api("/admin/document-types/reorder", {
        method: "POST",
        body: { ordered_ids: orderedIds },
      }),
    onSuccess: invalidate,
    onError: (e) => {
      onError(e, "Could not reorder — the list was restored");
      invalidate();
    },
  });

  return (
    <div className="card settings-form">
      <h2>Document types</h2>
      <p className="muted">
        The labels patients choose from when they upload a file to their case. Drag to
        set the order they appear in; deleting a type keeps it on already-uploaded
        files.
      </p>
      {error && <p className="error-text">{error}</p>}

      <form
        className="inline-form doc-type-form"
        onSubmit={(e) => {
          e.preventDefault();
          if (name.trim()) create.mutate();
        }}
      >
        <input
          className="input"
          placeholder="New document type (e.g. Police report)"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <button className="btn btn-primary" type="submit" disabled={!name.trim()}>
          Add
        </button>
      </form>

      {isLoading && <p className="muted">Loading…</p>}
      {data && data.length === 0 && (
        <p className="muted">
          No document types yet — patients won&apos;t see a label dropdown until you add
          some.
        </p>
      )}
      {data && data.length > 0 && (
        <div className="doc-type-list">
          <SortableList
            items={data}
            onReorder={(ids) => reorder.mutate(ids)}
            renderItem={(t) => (
              <div className="doc-type-row">
                <span className="doc-type-name">{t.name}</span>
                <button
                  className="btn btn-danger"
                  onClick={() => {
                    if (confirm(`Delete "${t.name}"? Existing files keep the label.`))
                      remove.mutate(t.id);
                  }}
                >
                  Delete
                </button>
              </div>
            )}
          />
        </div>
      )}
    </div>
  );
}

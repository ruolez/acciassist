import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../../api/client";
import type { InjuryType } from "../../api/types";
import { SortableList } from "./SortableList";
import "./admin.css";

const KEY = ["admin", "injury-types"];

export function InjuryTypesPage() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: KEY,
    queryFn: () => api<InjuryType[]>("/admin/injury-types"),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: KEY });

  const create = useMutation({
    mutationFn: () =>
      api("/admin/injury-types", {
        method: "POST",
        body: { name, description: description || null, is_published: false },
      }),
    onSuccess: () => {
      setName("");
      setDescription("");
      invalidate();
    },
  });

  const update = useMutation({
    mutationFn: (it: InjuryType) =>
      api(`/admin/injury-types/${it.id}`, {
        method: "PUT",
        body: { name: it.name, description: it.description, is_published: it.is_published },
      }),
    onSuccess: invalidate,
  });

  const remove = useMutation({
    mutationFn: (id: number) => api(`/admin/injury-types/${id}`, { method: "DELETE" }),
    onSuccess: invalidate,
  });

  const reorder = useMutation({
    mutationFn: (orderedIds: number[]) =>
      api("/admin/injury-types/reorder", { method: "POST", body: { ordered_ids: orderedIds } }),
    onSuccess: invalidate,
  });

  return (
    <div className="page">
      <div className="page-head">
        <h1>Injury Types</h1>
      </div>

      <form
        className="card inline-form"
        onSubmit={(e) => {
          e.preventDefault();
          if (name.trim()) create.mutate();
        }}
      >
        <input
          className="input"
          placeholder="New injury type (e.g. Slip and Fall)"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <input
          className="input"
          placeholder="Short description (optional)"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
        <button className="btn btn-primary" type="submit" disabled={!name.trim()}>
          Add
        </button>
      </form>

      {isLoading && <p className="muted">Loading…</p>}
      {data && data.length === 0 && <p className="muted">No injury types yet.</p>}

      {data && (
        <SortableList
          items={data}
          onReorder={(ids) => reorder.mutate(ids)}
          renderItem={(it) => (
            <div className="it-row">
              <div className="it-main">
                <span className="it-name">{it.name}</span>
                <span className="muted it-slug">/{it.slug}</span>
                <span className={`badge ${it.is_published ? "badge-on" : "badge-off"}`}>
                  {it.is_published ? "Published" : "Draft"}
                </span>
              </div>
              <div className="it-actions">
                <Link className="btn btn-outline" to={`/admin/injury-types/${it.id}/questions`}>
                  Questions
                </Link>
                <Link className="btn btn-outline" to={`/admin/injury-types/${it.id}/summary`}>
                  Summary
                </Link>
                <button
                  className="btn btn-ghost"
                  onClick={() => update.mutate({ ...it, is_published: !it.is_published })}
                >
                  {it.is_published ? "Unpublish" : "Publish"}
                </button>
                <button
                  className="btn btn-danger"
                  onClick={() => {
                    if (confirm(`Delete "${it.name}" and all its questions?`)) remove.mutate(it.id);
                  }}
                >
                  Delete
                </button>
              </div>
            </div>
          )}
        />
      )}
    </div>
  );
}

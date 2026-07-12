import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { api, ApiError } from "../../api/client";
import type { AppSettings, EmailLogEntry, OpenRouterModel } from "../../api/types";
import { useActionError } from "./useActionError";
import "./admin.css";

const KEY = ["admin", "settings"];

type FormState = {
  smtp_host: string;
  smtp_port: string;
  smtp_username: string;
  smtp_password: string;
  smtp_tls_mode: "none" | "starttls" | "ssl";
  from_email: string;
  from_name: string;
  app_base_url: string;
  openrouter_api_key: string;
  openrouter_model: string;
};

function toForm(s: AppSettings): FormState {
  return {
    smtp_host: s.smtp_host ?? "",
    smtp_port: String(s.smtp_port),
    smtp_username: s.smtp_username ?? "",
    smtp_password: "",
    smtp_tls_mode: s.smtp_tls_mode,
    from_email: s.from_email ?? "",
    from_name: s.from_name,
    app_base_url: s.app_base_url ?? "",
    openrouter_api_key: "",
    openrouter_model: s.openrouter_model ?? "",
  };
}

function ModelSelect({
  keySaved,
  value,
  onSelect,
}: {
  keySaved: boolean;
  value: string;
  onSelect: (id: string) => void;
}) {
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState(false);
  const { data: models, isLoading, isError } = useQuery({
    queryKey: ["admin", "ai", "models"],
    queryFn: () => api<OpenRouterModel[]>("/admin/ai/models"),
    enabled: keySaved,
    staleTime: 5 * 60 * 1000,
  });

  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!models) return [];
    if (!needle) return models;
    return models.filter(
      (m) => m.id.toLowerCase().includes(needle) || m.name.toLowerCase().includes(needle),
    );
  }, [models, search]);

  if (!keySaved) {
    return <p className="muted">Save an API key first to load the model list.</p>;
  }
  if (isLoading) return <p className="muted">Loading models…</p>;
  if (isError) {
    return <p className="error-text">Could not load models — check the API key.</p>;
  }

  return (
    <div className="model-select">
      <input
        className="input"
        value={open ? search : value || search}
        placeholder="Search models — e.g. claude, gpt, gemini"
        onFocus={() => setOpen(true)}
        onChange={(e) => {
          setSearch(e.target.value);
          setOpen(true);
        }}
      />
      {open && (
        <div className="model-list">
          {filtered.slice(0, 50).map((m) => (
            <button
              key={m.id}
              type="button"
              className={`model-row${m.id === value ? " selected" : ""}`}
              onClick={() => {
                onSelect(m.id);
                setSearch("");
                setOpen(false);
              }}
            >
              <span className="model-name">{m.name}</span>
              <span className="model-meta">
                {m.id}
                {m.context_length ? ` · ${Math.round(m.context_length / 1000)}k ctx` : ""}
                {m.prompt_price ? ` · $${m.prompt_price}/M in` : ""}
                {m.completion_price ? ` · $${m.completion_price}/M out` : ""}
              </span>
            </button>
          ))}
          {filtered.length === 0 && <p className="muted model-empty">No models match.</p>}
        </div>
      )}
    </div>
  );
}

export function SettingsPage() {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<FormState | null>(null);
  const [testTo, setTestTo] = useState("");
  const [testResult, setTestResult] = useState<string | null>(null);
  const [aiTestResult, setAiTestResult] = useState<string | null>(null);
  const { error, onError, clear } = useActionError();

  const { data } = useQuery({ queryKey: KEY, queryFn: () => api<AppSettings>("/admin/settings") });
  const { data: log } = useQuery({
    queryKey: [...KEY, "email-log"],
    queryFn: () => api<EmailLogEntry[]>("/admin/settings/email-log"),
  });

  useEffect(() => {
    if (data && form === null) setForm(toForm(data));
  }, [data, form]);

  const save = useMutation({
    mutationFn: (f: FormState) =>
      api<AppSettings>("/admin/settings", {
        method: "PUT",
        body: {
          smtp_host: f.smtp_host || null,
          smtp_port: Number(f.smtp_port) || 587,
          smtp_username: f.smtp_username || null,
          // Empty field means "keep current password"; type a value to change it.
          smtp_password: f.smtp_password === "" ? null : f.smtp_password,
          smtp_tls_mode: f.smtp_tls_mode,
          from_email: f.from_email || null,
          from_name: f.from_name || "AcciAssist",
          app_base_url: f.app_base_url || null,
          // Empty field means "keep current key"; type a value to change it.
          openrouter_api_key: f.openrouter_api_key === "" ? null : f.openrouter_api_key,
          openrouter_model: f.openrouter_model || null,
        },
      }),
    onSuccess: (saved) => {
      clear();
      queryClient.setQueryData(KEY, saved);
      setForm(toForm(saved));
    },
    onError: (e) => onError(e, "Could not save settings"),
  });

  const sendTest = useMutation({
    mutationFn: () =>
      api("/admin/settings/test-email", { method: "POST", body: { to_email: testTo } }),
    onSuccess: () => setTestResult("Test email sent — check the inbox."),
    onError: (e) =>
      setTestResult(
        `Failed: ${e instanceof ApiError ? e.message : "unexpected error"}`,
      ),
    onSettled: () =>
      queryClient.invalidateQueries({ queryKey: [...KEY, "email-log"] }),
  });

  const testAi = useMutation({
    mutationFn: () =>
      api<{ ok: boolean; model: string; reply: string }>("/admin/ai/test", { method: "POST" }),
    onSuccess: (r) => setAiTestResult(`Connected — ${r.model} replied "${r.reply}".`),
    onError: (e) =>
      setAiTestResult(`Failed: ${e instanceof ApiError ? e.message : "unexpected error"}`),
  });

  if (!form) return <div className="page muted">Loading…</div>;

  const set = (patch: Partial<FormState>) => setForm({ ...form, ...patch });

  return (
    <div className="page">
      <div className="page-head">
        <h1>Settings</h1>
      </div>
      {error && <p className="error-text">{error}</p>}

      <form
        className="card settings-form"
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate(form);
        }}
      >
        <h2>Email (SMTP)</h2>
        <p className="muted">
          Used to send case confirmations, account links, and progress notifications.
        </p>
        <div className="settings-grid">
          <div className="field">
            <label>SMTP host</label>
            <input
              className="input"
              value={form.smtp_host}
              onChange={(e) => set({ smtp_host: e.target.value })}
              placeholder="smtp.example.com"
            />
          </div>
          <div className="field">
            <label>Port</label>
            <input
              className="input"
              type="number"
              value={form.smtp_port}
              onChange={(e) => set({ smtp_port: e.target.value })}
            />
          </div>
          <div className="field">
            <label>Encryption</label>
            <select
              className="select"
              value={form.smtp_tls_mode}
              onChange={(e) =>
                set({ smtp_tls_mode: e.target.value as FormState["smtp_tls_mode"] })
              }
            >
              <option value="starttls">STARTTLS (587)</option>
              <option value="ssl">SSL/TLS (465)</option>
              <option value="none">None</option>
            </select>
          </div>
          <div className="field">
            <label>Username</label>
            <input
              className="input"
              value={form.smtp_username}
              onChange={(e) => set({ smtp_username: e.target.value })}
              autoComplete="off"
            />
          </div>
          <div className="field">
            <label>Password</label>
            <input
              className="input"
              type="password"
              value={form.smtp_password}
              onChange={(e) => set({ smtp_password: e.target.value })}
              placeholder={data?.smtp_password_set ? "•••••••• (saved)" : ""}
              autoComplete="new-password"
            />
          </div>
          <div className="field">
            <label>From email</label>
            <input
              className="input"
              type="email"
              value={form.from_email}
              onChange={(e) => set({ from_email: e.target.value })}
              placeholder="noreply@yourdomain.com"
            />
          </div>
          <div className="field">
            <label>From name</label>
            <input
              className="input"
              value={form.from_name}
              onChange={(e) => set({ from_name: e.target.value })}
            />
          </div>
          <div className="field">
            <label>Public site URL (used in email links)</label>
            <input
              className="input"
              value={form.app_base_url}
              onChange={(e) => set({ app_base_url: e.target.value })}
              placeholder="https://yourdomain.com"
            />
          </div>
        </div>
        <h2 className="settings-section-title">Case estimates (OpenRouter)</h2>
        <p className="muted">
          Answers from completed questionnaires are sent to this model to estimate the
          case cost and payout shown to clients and admins.
        </p>
        <div className="settings-grid">
          <div className="field">
            <label>OpenRouter API key</label>
            <input
              className="input"
              type="password"
              value={form.openrouter_api_key}
              onChange={(e) => set({ openrouter_api_key: e.target.value })}
              placeholder={data?.openrouter_api_key_set ? "•••••••• (saved)" : "sk-or-…"}
              autoComplete="new-password"
            />
          </div>
          <div className="field field-wide">
            <label>Model</label>
            <ModelSelect
              keySaved={Boolean(data?.openrouter_api_key_set)}
              value={form.openrouter_model}
              onSelect={(id) => set({ openrouter_model: id })}
            />
            {form.openrouter_model && (
              <p className="muted model-current">Selected: {form.openrouter_model}</p>
            )}
          </div>
        </div>
        <button className="btn btn-primary" type="submit" disabled={save.isPending}>
          {save.isSuccess && !save.isPending ? "Saved ✓" : "Save settings"}
        </button>
      </form>

      <div className="card settings-form">
        <h2>Test AI connection</h2>
        <p className="muted">Sends a one-line prompt to the selected model.</p>
        <div className="inline-form">
          <button
            className="btn btn-outline"
            disabled={testAi.isPending || !data?.openrouter_api_key_set}
            onClick={() => {
              setAiTestResult(null);
              testAi.mutate();
            }}
          >
            {testAi.isPending ? "Testing…" : "Run test"}
          </button>
        </div>
        {aiTestResult && (
          <p className={aiTestResult.startsWith("Failed") ? "error-text" : "success-text"}>
            {aiTestResult}
          </p>
        )}
      </div>

      <div className="card settings-form">
        <h2>Send a test email</h2>
        <div className="inline-form">
          <input
            className="input"
            type="email"
            placeholder="you@example.com"
            value={testTo}
            onChange={(e) => setTestTo(e.target.value)}
          />
          <button
            className="btn btn-outline"
            disabled={!testTo || sendTest.isPending}
            onClick={() => {
              setTestResult(null);
              sendTest.mutate();
            }}
          >
            {sendTest.isPending ? "Sending…" : "Send test"}
          </button>
        </div>
        {testResult && (
          <p className={testResult.startsWith("Failed") ? "error-text" : "success-text"}>
            {testResult}
          </p>
        )}
      </div>

      <div className="card settings-form">
        <h2>Recent emails</h2>
        {log && log.length === 0 && <p className="muted">Nothing sent yet.</p>}
        <div className="table-list">
          {log?.map((entry) => (
            <div key={entry.id} className="email-log-row">
              <span className={`badge email-${entry.status}`}>{entry.status}</span>
              <span className="lead-name">{entry.to_email}</span>
              <span className="muted">{entry.purpose}</span>
              <span className="muted">{new Date(entry.created_at).toLocaleString()}</span>
              {entry.error && <span className="error-text email-log-error">{entry.error}</span>}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

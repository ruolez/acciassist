import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, test, vi } from "vitest";

import type { CaseDetail, CaseDocument, User } from "../../api/types";
import { CaseDocumentsPage } from "./CaseDocumentsPage";
import { CaseInfoPage } from "./CaseInfoPage";
import { CaseLayout } from "./CaseLayout";
import { CaseOverviewPage } from "./CaseOverviewPage";
import { CaseUpdatesPage } from "./CaseUpdatesPage";

const apiMock = vi.hoisted(() => vi.fn());
vi.mock("../../api/client", () => ({
  api: apiMock,
  apiUpload: vi.fn(),
  ApiError: class ApiError extends Error {
    code = "err";
    status = 500;
  },
}));

const user: User = {
  id: 1,
  email: "pat@example.com",
  name: "Pat Smith",
  phone: null,
  created_at: "2026-07-01T00:00:00Z",
};

const caseDetail: CaseDetail = {
  id: 4,
  stage: "under_review",
  created_at: "2026-07-01T00:00:00Z",
  injury_type_name: "Slip & Fall",
  estimate_min: 5000,
  estimate_max: 25000,
  followup_pending: true,
  latest_update_body: null,
  latest_update_at: null,
  updates: [
    { id: 1, kind: "message", body: "We requested your records.", created_at: "2026-07-02T00:00:00Z" },
    { id: 2, kind: "stage_change", body: "Stage changed to Under review", created_at: "2026-07-03T00:00:00Z" },
  ],
  summary: null,
  name: "Pat Smith",
  email: "pat@example.com",
  phone: null,
  followup_total: 5,
  estimate_status: null,
  estimate_refined: false,
};

const documents: CaseDocument[] = [
  {
    id: 1,
    original_name: "bill.pdf",
    content_type: "application/pdf",
    size_bytes: 1000,
    created_at: "2026-07-02T00:00:00Z",
  },
  {
    id: 2,
    original_name: "photo.jpg",
    content_type: "image/jpeg",
    size_bytes: 2000,
    created_at: "2026-07-02T00:00:00Z",
  },
];

function renderAt(path: string, detail: CaseDetail | Error = caseDetail) {
  apiMock.mockImplementation((requested: string) => {
    if (requested === "/me/cases/4/documents") return Promise.resolve(documents);
    if (requested === "/me/cases") return Promise.resolve([{ id: 4 }, { id: 9 }]);
    if (requested === "/me/cases/4") {
      return detail instanceof Error ? Promise.reject(detail) : Promise.resolve(detail);
    }
    return Promise.reject(new Error(`unexpected ${requested}`));
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route element={<Outlet context={user} />}>
            <Route path="/account/cases/:caseId" element={<CaseLayout />}>
              <Route index element={<CaseOverviewPage />} />
              <Route path="documents" element={<CaseDocumentsPage />} />
              <Route path="updates" element={<CaseUpdatesPage />} />
              <Route path="details" element={<CaseInfoPage />} />
            </Route>
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("CaseLayout", () => {
  beforeEach(() => {
    apiMock.mockReset();
  });

  test("index route renders the overview with stage explainer", async () => {
    renderAt("/account/cases/4");
    expect(await screen.findByText(/What's happening now:/)).toBeInTheDocument();
    expect(screen.getByText("Slip & Fall · #4")).toBeInTheDocument();
  });

  test("exactly one nav link is active on the index route", async () => {
    const { container } = renderAt("/account/cases/4");
    await screen.findByText(/What's happening now:/);
    const active = container.querySelectorAll(".case-nav-link.active");
    expect(Array.from(active).map((el) => el.textContent)).toEqual(["Overview"]);
  });

  test("documents nav link shows the count badge and updates shows its count", async () => {
    renderAt("/account/cases/4/updates");
    await screen.findByText("We requested your records.");
    await waitFor(() => {
      const badges = document.querySelectorAll(".case-nav-badge");
      expect(Array.from(badges).map((b) => b.textContent)).toEqual(["2", "2"]);
    });
  });

  test("details route renders contact details", async () => {
    renderAt("/account/cases/4/details");
    expect(await screen.findByText("Your contact details")).toBeInTheDocument();
    expect(screen.getByText(/pat@example.com/)).toBeInTheDocument();
  });

  test("load failure shows an error with a way back", async () => {
    renderAt("/account/cases/4", new Error("boom"));
    expect(await screen.findByText(/couldn't load this case/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /back to your cases/i })).toBeInTheDocument();
  });
});

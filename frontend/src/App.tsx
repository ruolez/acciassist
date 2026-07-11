import { Navigate, Route, Routes } from "react-router-dom";

import { AccountLayout } from "./features/account/AccountLayout";
import { CaseDetailPage } from "./features/account/CaseDetailPage";
import { ClaimAccountPage } from "./features/account/ClaimAccountPage";
import { DashboardPage } from "./features/account/DashboardPage";
import { ForgotPasswordPage } from "./features/account/ForgotPasswordPage";
import { ResetPasswordPage } from "./features/account/ResetPasswordPage";
import { UserLogin } from "./features/account/UserLogin";
import { AdminLayout } from "./features/admin/AdminLayout";
import { AdminLogin } from "./features/admin/AdminLogin";
import { AdminsPage } from "./features/admin/AdminsPage";
import { CaseDetailAdminPage } from "./features/admin/CaseDetailAdminPage";
import { CasesPage } from "./features/admin/CasesPage";
import { InjuryTypesPage } from "./features/admin/InjuryTypesPage";
import { QuestionnaireBuilder } from "./features/admin/QuestionnaireBuilder";
import { SettingsPage } from "./features/admin/SettingsPage";
import { SubmissionsPage } from "./features/admin/SubmissionsPage";
import { SummaryTemplatePage } from "./features/admin/SummaryTemplatePage";
import { IntakeWizard } from "./features/intake/IntakeWizard";
import { LandingPage } from "./features/intake/LandingPage";
import { SummaryPage } from "./features/intake/SummaryPage";

export function App() {
  return (
    <Routes>
      {/* Public patient flow */}
      <Route path="/" element={<LandingPage />} />
      <Route path="/intake/:injuryTypeId" element={<IntakeWizard />} />
      <Route path="/intake/session/:sessionId/summary" element={<SummaryPage />} />

      {/* Client accounts */}
      <Route path="/login" element={<UserLogin />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/account/claim" element={<ClaimAccountPage />} />
      <Route path="/account" element={<AccountLayout />}>
        <Route index element={<DashboardPage />} />
        <Route path="cases/:caseId" element={<CaseDetailPage />} />
      </Route>

      {/* Admin */}
      <Route path="/admin/login" element={<AdminLogin />} />
      <Route path="/admin" element={<AdminLayout />}>
        <Route index element={<Navigate to="injury-types" replace />} />
        <Route path="injury-types" element={<InjuryTypesPage />} />
        <Route path="injury-types/:id/questions" element={<QuestionnaireBuilder />} />
        <Route path="injury-types/:id/summary" element={<SummaryTemplatePage />} />
        <Route path="submissions" element={<SubmissionsPage />} />
        <Route path="cases" element={<CasesPage />} />
        <Route path="cases/:caseId" element={<CaseDetailAdminPage />} />
        <Route path="admins" element={<AdminsPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

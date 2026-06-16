import { Navigate, Route, Routes } from "react-router-dom";

import { AdminLayout } from "./features/admin/AdminLayout";
import { AdminLogin } from "./features/admin/AdminLogin";
import { AdminsPage } from "./features/admin/AdminsPage";
import { InjuryTypesPage } from "./features/admin/InjuryTypesPage";
import { LeadsPage } from "./features/admin/LeadsPage";
import { QuestionnaireBuilder } from "./features/admin/QuestionnaireBuilder";
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

      {/* Admin */}
      <Route path="/admin/login" element={<AdminLogin />} />
      <Route path="/admin" element={<AdminLayout />}>
        <Route index element={<Navigate to="injury-types" replace />} />
        <Route path="injury-types" element={<InjuryTypesPage />} />
        <Route path="injury-types/:id/questions" element={<QuestionnaireBuilder />} />
        <Route path="injury-types/:id/summary" element={<SummaryTemplatePage />} />
        <Route path="submissions" element={<SubmissionsPage />} />
        <Route path="leads" element={<LeadsPage />} />
        <Route path="admins" element={<AdminsPage />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

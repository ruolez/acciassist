import { useParams } from "react-router-dom";

import { usePageTitle } from "../../lib/usePageTitle";
import { useCaseContext } from "./CaseLayout";
import { DocumentsSection } from "./DocumentsSection";
import "./account.css";

export function CaseDocumentsPage() {
  const { caseId } = useParams();
  const { caseDetail } = useCaseContext();
  usePageTitle(`Documents · Case #${caseDetail.id}`, "AcciAssist");
  if (!caseId) return null;
  return <DocumentsSection caseId={caseId} />;
}

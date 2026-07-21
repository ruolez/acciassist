import { usePageTitle } from "../../lib/usePageTitle";
import { useCaseContext } from "./CaseLayout";
import "./account.css";

export function CaseInfoPage() {
  const { caseDetail: data } = useCaseContext();
  usePageTitle(`Case details · Case #${data.id}`, "AcciAssist");

  return (
    <>
      {data.summary && (
        <div className="portal-section portal-section-first">
          <h2>Your intake summary</h2>
          <details className="card summary-details">
            <summary>Show what you told us</summary>
            <div className="summary-body">{data.summary.body}</div>
          </details>
        </div>
      )}

      <div className="portal-section">
        <h2>Your contact details</h2>
        <div className="card contact-card">
          <p className="contact-lines">
            {data.name}
            <br />
            {data.email}
            {data.phone && (
              <>
                <br />
                {data.phone}
              </>
            )}
          </p>
          <p className="muted contact-note">
            This is how we reach you about your case. If anything changes, reply to any
            of our emails and we&apos;ll update it.
          </p>
        </div>
      </div>
    </>
  );
}

import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { Logo } from "../../components/Logo";
import "./legal.css";

function LegalLayout({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="legal-page">
      <header className="legal-topbar">
        <Logo size={34} withWordmark to="/" />
        <Link className="legal-back" to="/">
          ← Back to home
        </Link>
      </header>
      <main className="legal-body">
        <h1>{title}</h1>
        <p className="legal-updated">Last updated: July 2026</p>
        {children}
      </main>
      <footer className="legal-foot">
        <span>© 2026 AcciAssist. All rights reserved.</span>
        <nav className="legal-foot-links">
          <Link to="/privacy">Privacy policy</Link>
          <Link to="/terms">Terms of use</Link>
        </nav>
      </footer>
    </div>
  );
}

export function PrivacyPage() {
  return (
    <LegalLayout title="Privacy policy">
      <p>
        AcciAssist exists to give you an honest picture of your injury case. That only works
        if you can trust us with the details — so we keep this policy short, plain, and
        honest too.
      </p>

      <h2>What we collect</h2>
      <p>
        When you complete an assessment, we collect the answers you provide about your
        accident and injuries. You can complete the assessment anonymously. If you choose to
        work with us, we also collect the contact details you provide (such as your name and
        email address) and any documents you later share with our team. Like most websites,
        our servers keep routine technical logs (such as IP addresses) for security.
      </p>

      <h2>How we use it</h2>
      <p>
        Your information is used to prepare your case summary and estimate, to review your
        case if you ask us to, and to communicate with you about it. We do not sell your
        information, and we do not share it with advertisers.
      </p>

      <h2>Cookies</h2>
      <p>
        We use only the cookies needed for the site to work — for example, to keep you
        signed in to your client portal. We do not use advertising or cross-site tracking
        cookies.
      </p>

      <h2>How long we keep it</h2>
      <p>
        We keep assessment and case information for as long as it is needed to provide the
        service and to meet our legal obligations. If you would like your information
        removed, contact us through your client portal and we will handle your request.
      </p>

      <h2>How we protect it</h2>
      <p>
        Your information is encrypted in transit, stored on access-controlled systems, and
        visible only to the team members who need it to work on your case.
      </p>

      <h2>Your choices</h2>
      <p>
        You can complete an assessment without creating an account or providing contact
        details. If you have an account, you can ask us at any time to correct or delete the
        information we hold about you.
      </p>

      <h2>Changes to this policy</h2>
      <p>
        If we change this policy, we will update this page and the date above. Significant
        changes will be communicated to account holders directly.
      </p>
    </LegalLayout>
  );
}

export function TermsPage() {
  return (
    <LegalLayout title="Terms of use">
      <p>
        These terms cover your use of the AcciAssist website and services. By using the
        site, you agree to them.
      </p>

      <h2>What AcciAssist is</h2>
      <p>
        AcciAssist is a service that helps you understand and pursue your injury claim. It
        guides you through questions about your accident and produces a plain-English
        summary and an estimated value range for your case.
      </p>

      <h2>Not legal advice</h2>
      <p>
        AcciAssist is not a law firm, and using it does not create an attorney–client
        relationship. Estimates are informational only: they are based on the details you
        share and on general rules for your state, and they are not a promise or guarantee
        of any settlement, payout, or outcome. You are always free to consult an attorney.
      </p>

      <h2>Your responsibilities</h2>
      <p>
        The quality of your summary and estimate depends on the accuracy of your answers.
        You agree to provide information that is truthful and complete to the best of your
        knowledge, and to use the service only for your own genuine claim.
      </p>

      <h2>Accounts</h2>
      <p>
        An account is only needed if you choose to work with us. You are responsible for
        keeping your login credentials private. We may suspend accounts used fraudulently or
        abusively.
      </p>

      <h2>Limitation of liability</h2>
      <p>
        We work hard to make the service accurate and reliable, but it is provided “as is.”
        To the fullest extent permitted by law, AcciAssist is not liable for decisions made
        in reliance on an informational estimate, or for indirect or consequential damages
        arising from use of the site.
      </p>

      <h2>Changes to these terms</h2>
      <p>
        If we change these terms, we will update this page and the date above. Continued use
        of the service after a change means you accept the updated terms.
      </p>
    </LegalLayout>
  );
}

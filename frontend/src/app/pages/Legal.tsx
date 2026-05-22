/**
 * Privacy / Terms / Cookies pages.
 *
 * These exist mainly because:
 *   1. Google OAuth requires a public privacy policy URL before the
 *      OAuth consent screen can leave testing mode.
 *   2. Firebase Hosting's domain verification and most app stores
 *      reject deploys without these links.
 *   3. GDPR / CCPA compliance — even if you're US-only today, EU
 *      visitors will reach the site and we owe them a clear policy.
 *
 * The content here is *baseline*. Before sending real users through
 * signup, route this copy past your lawyer and replace the placeholder
 * dates and contact email at the bottom of each page.
 */

import { Link } from "react-router";

const F = "'Plus Jakarta Sans', sans-serif";
const T = {
  text: "#F2EEB3",
  t2: "rgba(242,238,179,0.75)",
  t3: "rgba(242,238,179,0.55)",
  border: "rgba(242,238,179,0.12)",
};

const SHELL: React.CSSProperties = {
  maxWidth: 760,
  margin: "0 auto",
  padding: "48px 24px 80px",
  color: T.text,
  fontFamily: F,
  lineHeight: 1.6,
};

const H1: React.CSSProperties = { fontSize: 28, fontWeight: 700, marginBottom: 6 };
const META: React.CSSProperties = { fontSize: 12, color: T.t3, marginBottom: 24 };
const H2: React.CSSProperties = { fontSize: 17, fontWeight: 700, marginTop: 28, marginBottom: 8 };
const P: React.CSSProperties = { fontSize: 14, color: T.t2, marginBottom: 12 };

function LegalShell({
  title,
  updated,
  children,
}: {
  title: string;
  updated: string;
  children: React.ReactNode;
}) {
  return (
    <main role="main" style={SHELL}>
      <nav aria-label="breadcrumb" style={{ fontSize: 12, color: T.t3, marginBottom: 16 }}>
        <Link to="/" style={{ color: T.t3, textDecoration: "none" }}>← Back home</Link>
      </nav>
      <h1 style={H1}>{title}</h1>
      <div style={META}>Last updated: {updated}</div>
      <div style={{ borderTop: `1px solid ${T.border}`, paddingTop: 18 }}>{children}</div>
      <footer style={{ marginTop: 40, paddingTop: 20, borderTop: `1px solid ${T.border}`, fontSize: 12, color: T.t3 }}>
        Questions? Email{" "}
        <a href="mailto:legal@placeup.careers" style={{ color: T.text }}>
          legal@placeup.careers
        </a>
        .
        <div style={{ marginTop: 8, display: "flex", gap: 14, flexWrap: "wrap" }}>
          <Link to="/privacy" style={{ color: T.t3 }}>Privacy</Link>
          <Link to="/terms" style={{ color: T.t3 }}>Terms</Link>
          <Link to="/cookies" style={{ color: T.t3 }}>Cookies</Link>
        </div>
      </footer>
    </main>
  );
}

export function PrivacyPage() {
  return (
    <LegalShell title="Privacy Policy" updated="May 21, 2026">
      <p style={P}>
        PlaceUp Careers ("we", "us") helps job seekers find visa-friendly roles
        by scoring scraped job postings against an uploaded resume. This page
        describes what we collect, why, and how to remove your data.
      </p>

      <h2 style={H2}>1. What we collect</h2>
      <p style={P}>
        Account data (email, name, optional LinkedIn URL, password hash) and
        resume content you upload (file metadata, parsed text used for
        scoring). We also collect application status notes you record against
        jobs you have applied to.
      </p>

      <h2 style={H2}>2. How we use it</h2>
      <p style={P}>
        To compute resume-to-job match scores, to surface visa-relevant
        postings, to maintain your application tracker, and to send the
        notifications you opt into. We do not sell your data and we do not
        share resume contents with employers or third-party brokers.
      </p>

      <h2 style={H2}>3. Where it lives</h2>
      <p style={P}>
        Account and resume data is stored in Google Cloud Firestore (regional
        US). Aggregated, non-PII job analytics live in Google Cloud SQL
        (PostgreSQL). Backups are retained for 30 days then deleted.
      </p>

      <h2 style={H2}>4. Your controls</h2>
      <p style={P}>
        From the dashboard you can delete individual resumes, change your
        password, and request a full account deletion. Deletion removes
        active records immediately; backups roll off within 30 days.
      </p>

      <h2 style={H2}>5. Cookies and analytics</h2>
      <p style={P}>
        See our <Link to="/cookies" style={{ color: T.text }}>Cookies notice</Link>{" "}
        for the full list. We do not use third-party advertising trackers.
      </p>

      <h2 style={H2}>6. Contact</h2>
      <p style={P}>
        Email <a href="mailto:privacy@placeup.careers" style={{ color: T.text }}>privacy@placeup.careers</a>{" "}
        for any data-subject request (access, correction, deletion). We will
        respond within 30 days.
      </p>
    </LegalShell>
  );
}

export function TermsPage() {
  return (
    <LegalShell title="Terms of Service" updated="May 21, 2026">
      <p style={P}>
        By creating a PlaceUp Careers account you agree to these terms. They
        cover what the service does, what you can and cannot do on it, and
        the limits of our liability.
      </p>

      <h2 style={H2}>1. The service</h2>
      <p style={P}>
        PlaceUp scrapes public job postings and computes a match score
        against the resume you provide. We do not represent that any
        specific job is open, available to you, or that any visa
        classification is guaranteed.
      </p>

      <h2 style={H2}>2. Your account</h2>
      <p style={P}>
        You are responsible for keeping your password safe and for everything
        that happens under your account. Notify us immediately at{" "}
        <a href="mailto:security@placeup.careers" style={{ color: T.text }}>
          security@placeup.careers
        </a>{" "}
        if you believe your account has been compromised.
      </p>

      <h2 style={H2}>3. Acceptable use</h2>
      <p style={P}>
        Do not abuse the service — no automated scraping of our pages, no
        attempts to access other users' data, no uploading of content you
        do not have rights to. We may suspend accounts that violate this.
      </p>

      <h2 style={H2}>4. No warranties</h2>
      <p style={P}>
        The service is provided "as is". Job postings come from third-party
        sources that may be inaccurate, stale, or removed. We are not
        responsible for hiring outcomes.
      </p>

      <h2 style={H2}>5. Limitation of liability</h2>
      <p style={P}>
        To the maximum extent permitted by law, PlaceUp is not liable for
        indirect, incidental, special, consequential, or punitive damages
        arising from your use of the service.
      </p>

      <h2 style={H2}>6. Changes</h2>
      <p style={P}>
        We may update these terms; the "last updated" date at the top
        reflects the most recent revision. Continued use after a change
        means you accept the new terms.
      </p>
    </LegalShell>
  );
}

export function CookiesPage() {
  return (
    <LegalShell title="Cookies & Local Storage" updated="May 21, 2026">
      <p style={P}>
        PlaceUp uses a small number of browser-local storage entries to keep
        you signed in and remember your preferences. We do not load
        third-party ad cookies.
      </p>

      <h2 style={H2}>What we store on your device</h2>
      <p style={P}>
        <strong>Auth token</strong> — JWT issued at sign-in. Sent to the
        PlaceUp API in the <code>Authorization</code> header so we know
        who is making each request. Cleared on sign-out.
      </p>
      <p style={P}>
        <strong>Saved jobs</strong> — list of job IDs you bookmarked, kept
        client-side so the UI can show a "saved" badge without a roundtrip.
      </p>
      <p style={P}>
        <strong>Resume version</strong> — a cache buster that nudges other
        tabs to refresh when you upload a new resume.
      </p>

      <h2 style={H2}>How to clear it</h2>
      <p style={P}>
        Sign out, or clear site data from your browser's Application /
        Storage panel. There are no server-side cookies you need to
        revoke separately.
      </p>
    </LegalShell>
  );
}

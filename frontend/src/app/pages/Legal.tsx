/**
 * Legal pages: Privacy, Terms, Cookies, Disclaimer, Return Policy.
 *
 * Public pages required for compliance, OAuth consent, and app-store /
 * hosting checks. Copy is launch-grade and PlaceUp-specific. Have counsel do a
 * final review for your jurisdiction; the structure and routes are stable.
 */

import { Link } from "react-router";

const F = "'Plus Jakarta Sans', sans-serif";
const T = {
  text: "var(--pu-f1f5f9-t)",
  t2: "var(--pu-148-163-184-075)",
  t3: "var(--pu-148-163-184-055)",
  border: "var(--pu-148-163-184-012)",
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
        <a href="mailto:legal@placeupcareer.com" style={{ color: T.text }}>
          legal@placeupcareer.com
        </a>
        .
        <div style={{ marginTop: 8, display: "flex", gap: 14, flexWrap: "wrap" }}>
          <Link to="/privacy" style={{ color: T.t3 }}>Privacy</Link>
          <Link to="/terms" style={{ color: T.t3 }}>Terms</Link>
          <Link to="/cookies" style={{ color: T.t3 }}>Cookies</Link>
          <Link to="/disclaimer" style={{ color: T.t3 }}>Disclaimer</Link>
          <Link to="/return-policy" style={{ color: T.t3 }}>Return Policy</Link>
        </div>
      </footer>
    </main>
  );
}

export function PrivacyPage() {
  return (
    <LegalShell title="Privacy Policy" updated="June 21, 2026">
      <p style={P}>
        Place Up Career LLC ("PlaceUp", "we", "us") helps international and
        visa-sponsorship-seeking candidates find roles across multiple countries.
        This page describes what we collect, why, and how to control your data.
        Where a finalized policy is published, it governs.
      </p>

      <h2 style={H2}>1. What we collect</h2>
      <p style={P}>
        Account data (name, email, phone, password hash, optional LinkedIn URL),
        résumé content you upload (parsed text used for analysis), your job
        preferences and work-authorization/visa status, selected plan and
        payment status, and usage/device data. Card details are handled by the
        payment processor, and we do not store card numbers.
      </p>

      <h2 style={H2}>2. How we use it</h2>
      <p style={P}>
        To create and manage your account, analyze your résumé against postings
        (match scores, ATS analysis, visa signals), maintain your application
        tracker, and send notifications you opt into. We do not sell your data.
      </p>

      <h2 style={H2}>3. AI and third-party processing</h2>
      <p style={P}>
        Some features process your résumé content using third-party AI providers
        to generate informational estimates. You can opt out, in which case we
        use our own non-AI methods. We use service providers including Google
        Cloud, Cloudflare, OpenRouter, and our email provider.
      </p>

      <h2 style={H2}>4. Your controls</h2>
      <p style={P}>
        You can update your information, delete résumés, change your password,
        and request account and data deletion by emailing{" "}
        <a href="mailto:privacy@placeupcareer.com" style={{ color: T.text }}>privacy@placeupcareer.com</a>.
        We respond within the timeframe required by applicable law.
      </p>

      <h2 style={H2}>5. Cookies and analytics</h2>
      <p style={P}>
        See our <Link to="/cookies" style={{ color: T.text }}>Cookies notice</Link>{" "}
        for details. Non-essential analytics load only after consent. We do not
        use third-party advertising trackers.
      </p>

      <h2 style={H2}>6. Legal bases for processing</h2>
      <p style={P}>
        Where the GDPR applies, we process your data to perform our contract with
        you (providing the service), on the basis of your consent (optional
        analytics and AI processing, which you can withdraw at any time), and for
        our legitimate interests in operating, securing, and improving PlaceUp.
      </p>

      <h2 style={H2}>7. Data retention</h2>
      <p style={P}>
        We keep account and résumé data for as long as your account is active.
        After you request deletion, we remove your personal data within 30 days,
        except where we must retain limited records to meet legal, tax,
        accounting, fraud-prevention, or dispute-resolution obligations. Signed
        acceptance records (date, version, IP) are retained to evidence the
        agreement for as long as legally required.
      </p>

      <h2 style={H2}>8. International data transfers</h2>
      <p style={P}>
        We use cloud infrastructure that may process data in the United States and
        other countries. Where we transfer personal data out of the EEA or UK, we
        rely on appropriate safeguards such as the European Commission's Standard
        Contractual Clauses (and the UK Addendum) with our processors.
      </p>

      <h2 style={H2}>9. Security</h2>
      <p style={P}>
        We protect your data with encryption in transit (HTTPS/TLS), hashed
        passwords, access controls, and least-privilege practices. No method of
        transmission or storage is perfectly secure, but we take reasonable
        technical and organizational measures and will notify you and any
        regulator as required by law in the event of a breach affecting your
        personal data.
      </p>

      <h2 style={H2}>10. Your regional rights</h2>
      <p style={P}>
        Depending on where you live, you may have the right to access, correct,
        delete, port, or restrict processing of your data, to object to
        processing, and to withdraw consent (EEA/UK GDPR). California residents
        may request access to and deletion of personal information and may opt out
        of "sale" or "sharing" — we do not sell or share personal information as
        those terms are defined under the CCPA/CPRA. To exercise any right, email{" "}
        <a href="mailto:privacy@placeupcareer.com" style={{ color: T.text }}>privacy@placeupcareer.com</a>.
        You also have the right to lodge a complaint with your local supervisory
        authority.
      </p>

      <h2 style={H2}>11. Children</h2>
      <p style={P}>
        PlaceUp is intended for users aged 18 and over. We do not knowingly
        collect personal data from anyone under 18. If you believe a minor has
        provided us data, contact us and we will delete it.
      </p>

      <h2 style={H2}>12. Changes to this policy</h2>
      <p style={P}>
        We may update this Privacy Policy from time to time. The "last updated"
        date above reflects the most recent revision, and we will notify you of
        material changes through the service or by email.
      </p>

      <h2 style={H2}>13. Contact</h2>
      <p style={P}>
        Place Up Career LLC is the data controller. Email{" "}
        <a href="mailto:privacy@placeupcareer.com" style={{ color: T.text }}>privacy@placeupcareer.com</a>{" "}
        for any data-subject request (access, correction, deletion) or privacy
        question.
      </p>
    </LegalShell>
  );
}

export function TermsPage() {
  return (
    <LegalShell title="Terms of Service" updated="June 21, 2026">
      <p style={P}>
        By creating a PlaceUp account you agree to these Terms, operated by Place
        Up Career LLC. They cover the service, acceptable use, subscriptions,
        disclaimers, and dispute resolution.
      </p>

      <h2 style={H2}>1. The service</h2>
      <p style={P}>
        PlaceUp aggregates public job postings and provides résumé analysis and
        visa-sponsorship signals. We provide software and tools only; we are not
        an employer or staffing agency and are not party to any employment.
      </p>

      <h2 style={H2}>2. No guarantee of outcomes</h2>
      <p style={P}>
        We do not guarantee interviews, callbacks, offers, visa sponsorship, or
        employment. All match, sponsorship, and approval indicators are
        informational estimates, not guarantees or legal/immigration advice.
        See our <Link to="/disclaimer" style={{ color: T.text }}>Disclaimer</Link>.
      </p>

      <h2 style={H2}>3. Your account & acceptable use</h2>
      <p style={P}>
        You must be 18+ and provide accurate information. Do not scrape or resell
        our data, misrepresent your identity or work-authorization status, share
        accounts, or attempt to access other users' data. We may suspend
        accounts that violate these Terms.
      </p>

      <h2 style={H2}>4. Plans, billing, and launch preview</h2>
      <p style={P}>
        PlaceUp offers monthly Basic, Pro, and Elite plans. During launch
        preview, checkout may not be required immediately, but your selected
        plan can still be used for access limits, support routing, and future
        billing setup. We will not charge you unless a hosted checkout or other
        payment authorization clearly presents the amount and you complete it.
      </p>

      <h2 style={H2}>5. Disclaimers & limitation of liability</h2>
      <p style={P}>
        The Services are provided "as is" without warranties. To the maximum
        extent permitted by law, our total liability is limited to the amount you
        paid us in the six (6) months before the claim, or USD $100 where no
        payment was made, and we are not liable for indirect or consequential damages.
      </p>

      <h2 style={H2}>6. Governing law & disputes</h2>
      <p style={P}>
        These Terms are governed by the laws of the State of Wyoming. Disputes
        are resolved by informal negotiation, then binding arbitration in
        Sheridan County, Wyoming, on an individual basis (no class actions).
      </p>

      <h2 style={H2}>7. Your content & license</h2>
      <p style={P}>
        You retain ownership of the résumés and information you upload. You grant
        us a limited, non-exclusive license to store and process that content
        solely to operate the Services for you (parsing, matching, ATS and visa
        analysis). You are responsible for ensuring you have the right to upload
        anything you submit and that it is accurate.
      </p>

      <h2 style={H2}>8. Intellectual property</h2>
      <p style={P}>
        The PlaceUp platform, software, branding, and original content are owned
        by Place Up Career LLC and protected by intellectual-property laws. We
        grant you a personal, non-transferable, revocable license to use the
        Services; you may not copy, reverse-engineer, resell, or create derivative
        works without our written permission.
      </p>

      <h2 style={H2}>9. Third-party services & listings</h2>
      <p style={P}>
        Job listings are aggregated from public sources and employer career sites.
        We do not control third-party content or services and are not responsible
        for them. Your use of an employer's site is governed by that site's own terms.
      </p>

      <h2 style={H2}>10. Suspension & termination</h2>
      <p style={P}>
        You may stop using the Services and delete your account at any time. We may
        suspend or terminate access if you violate these Terms, misuse the
        Services, or where required by law. Sections that by their nature should
        survive termination (disclaimers, liability limits, dispute terms) will
        survive.
      </p>

      <h2 style={H2}>11. Indemnification</h2>
      <p style={P}>
        You agree to indemnify and hold harmless Place Up Career LLC from claims,
        losses, and expenses arising out of your misuse of the Services, your
        violation of these Terms, or your infringement of any third party's
        rights, to the extent permitted by law.
      </p>

      <h2 style={H2}>12. Severability & entire agreement</h2>
      <p style={P}>
        If any provision of these Terms is found unenforceable, the remaining
        provisions stay in effect. These Terms, together with the Privacy Policy,
        Disclaimer, Cookies notice, and Refund &amp; Cancellation Policy, form the
        entire agreement between you and us regarding the Services.
      </p>

      <h2 style={H2}>13. Changes</h2>
      <p style={P}>
        We may update these Terms and will notify users of material changes. The
        "last updated" date reflects the most recent revision; continued use after
        an update means you accept the revised Terms.
      </p>

      <h2 style={H2}>14. Contact</h2>
      <p style={P}>
        Questions about these Terms? Email{" "}
        <a href="mailto:legal@placeupcareer.com" style={{ color: T.text }}>legal@placeupcareer.com</a>.
      </p>
    </LegalShell>
  );
}

export function CookiesPage() {
  return (
    <LegalShell title="Cookies & Local Storage" updated="June 21, 2026">
      <p style={P}>
        PlaceUp uses cookies and browser storage to keep you signed in, remember
        preferences, and (with your consent) measure usage. We do not load
        third-party advertising cookies.
      </p>

      <h2 style={H2}>Essential storage</h2>
      <p style={P}>
        <strong>Auth token</strong> — keeps you signed in. <strong>Saved jobs</strong>{" "}
        — remembers bookmarked job IDs. <strong>Cookie consent</strong> — records
        your analytics choice. These are required for the service to work.
      </p>

      <h2 style={H2}>Analytics (consent-based)</h2>
      <p style={P}>
        With your consent, we use Google Analytics (with IP anonymization, no
        advertising features) to understand usage and improve the product. You
        can decline in the cookie banner, and analytics will not load.
      </p>

      <h2 style={H2}>How to clear it</h2>
      <p style={P}>
        Sign out, change your choice in the cookie banner, or clear site data
        from your browser's Application / Storage panel.
      </p>

      <h2 style={H2}>Managing consent & "Do Not Track"</h2>
      <p style={P}>
        You can withdraw or change your analytics consent at any time from the
        cookie banner; non-essential storage will not load until you opt in. We
        honor browser "Global Privacy Control" signals where required by law. For
        more on the personal data we process, see our{" "}
        <Link to="/privacy" style={{ color: T.text }}>Privacy Policy</Link>.
      </p>

      <h2 style={H2}>Changes & contact</h2>
      <p style={P}>
        We may update this notice as our cookie use changes. Questions? Email{" "}
        <a href="mailto:privacy@placeupcareer.com" style={{ color: T.text }}>privacy@placeupcareer.com</a>.
      </p>
    </LegalShell>
  );
}

export function DisclaimerPage() {
  return (
    <LegalShell title="Disclaimer" updated="June 21, 2026">
      <p style={P}>
        Place Up Career LLC ("PlaceUp", "we", "us") provides job-search tools,
        listings, and AI-assisted services for general informational purposes
        only.
      </p>

      <h2 style={H2}>1. No guarantee of results</h2>
      <p style={P}>
        We do not guarantee any interview, callback, assessment, recruiter
        response, job offer, visa sponsorship, work authorization, or employment.
        Results depend on factors outside our control, including your
        qualifications, employer decisions, market conditions, and location.
      </p>

      <h2 style={H2}>2. Visa & sponsorship information</h2>
      <p style={P}>
        Visa, work-authorization, and sponsorship indicators, "sponsor-friendly"
        tags, approval rates, match scores, ATS scores, and salary figures are
        automated, informational estimates from third-party data and heuristics.
        They may be incomplete, outdated, or inaccurate, and are not a promise
        that any employer will sponsor a visa or hire you. Verify sponsorship and
        all job details directly with the employer before relying on them.
      </p>

      <h2 style={H2}>3. Not legal or immigration advice</h2>
      <p style={P}>
        The Services do not provide legal, immigration, financial, or tax advice,
        and nothing in the Services should be treated as such. For advice about
        your situation, consult a qualified licensed professional.
      </p>

      <h2 style={H2}>4. Third-party listings</h2>
      <p style={P}>
        Many listings are aggregated from third-party sources and employer career
        sites. We do not control, verify, or guarantee their accuracy,
        availability, or current status, and a listing may be outdated, filled,
        or removed. We are not responsible for your dealings with any employer or
        third-party website.
      </p>

      <h2 style={H2}>5. Contact</h2>
      <p style={P}>
        Questions? Email{" "}
        <a href="mailto:legal@placeupcareer.com" style={{ color: T.text }}>legal@placeupcareer.com</a>.
      </p>
    </LegalShell>
  );
}

export function ReturnPolicyPage() {
  return (
    <LegalShell title="Refund & Cancellation Policy" updated="June 21, 2026">
      <p style={P}>
        This policy explains refunds and cancellation for paid PlaceUp plans.
        If checkout is unavailable during launch preview, there is no charge to
        refund or cancel until you complete a paid checkout.
      </p>

      <h2 style={H2}>1. 24-hour refund window</h2>
      <p style={P}>
        If you believe you were charged in error or need help with a recent
        paid checkout, email{" "}
        <a href="mailto:refund@placeupcareer.com" style={{ color: T.text }}>refund@placeupcareer.com</a>.
      </p>

      <h2 style={H2}>2. Cancellation & future charges</h2>
      <p style={P}>
        When a recurring subscription is active, you can request cancellation
        help by email or through any billing portal we provide. Cancellation
        stops future renewals but does not remove access already delivered for
        the paid period unless required by law.
      </p>

      <h2 style={H2}>3. Processing fees</h2>
      <p style={P}>
        Payment-processing fees may be non-refundable where permitted by law and
        by the payment processor's rules.
      </p>

      <h2 style={H2}>4. EU/UK consumers</h2>
      <p style={P}>
        If you are an EU or UK consumer, additional withdrawal rights may apply
        depending on when paid service begins and what you authorize at
        checkout. Any required consumer notices will be presented before paid
        checkout.
      </p>

      <h2 style={H2}>5. Contact</h2>
      <p style={P}>
        For refund or cancellation help, email{" "}
        <a href="mailto:refund@placeupcareer.com" style={{ color: T.text }}>refund@placeupcareer.com</a>.
      </p>
    </LegalShell>
  );
}

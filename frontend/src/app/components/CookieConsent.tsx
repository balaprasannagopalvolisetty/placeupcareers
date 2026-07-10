import { useEffect, useState } from "react";
import { consentStatus, setConsent, initAnalytics } from "../lib/analytics";

/**
 * GDPR/CCPA cookie-consent banner. Shown until the user accepts or declines.
 * Analytics only loads after "Accept" (handled in analytics.setConsent).
 */
export function CookieConsent() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const status = consentStatus();
    if (status === "granted") initAnalytics();
    if (status === "unset") setVisible(true);
  }, []);

  if (!visible) return null;

  const choose = (granted: boolean) => {
    setConsent(granted);
    setVisible(false);
  };

  return (
    <div
      role="dialog"
      aria-label="Cookie consent"
      style={{
        position: "fixed", left: 16, right: 16, bottom: 16, zIndex: 4000,
        maxWidth: 720, margin: "0 auto", display: "flex", gap: 14, flexWrap: "wrap",
        alignItems: "center", justifyContent: "space-between",
        background: "var(--pu-8-18-38-097)", border: "1px solid var(--pu-148-163-184-014)",
        borderRadius: 14, padding: "14px 18px", backdropFilter: "blur(20px)",
        boxShadow: "0 18px 48px var(--pu-1-17-38-05)", fontFamily: "'Plus Jakarta Sans', sans-serif",
      }}
    >
      <div style={{ flex: "1 1 320px", minWidth: 0, fontSize: 12.5, lineHeight: 1.55, color: "var(--pu-148-163-184-078)" }}>
        We use essential cookies to run PlaceUp and, with your consent, analytics
        cookies to improve it. See our{" "}
        <a href="/cookies" style={{ color: "var(--pu-3b82f6-t)", textDecoration: "none" }}>Cookies notice</a>.
      </div>
      <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
        <button
          onClick={() => choose(false)}
          style={{ padding: "9px 16px", borderRadius: 9, border: "1px solid var(--pu-148-163-184-016)", background: "transparent", color: "var(--pu-148-163-184-07)", fontSize: 12.5, fontWeight: 700, cursor: "pointer", fontFamily: "inherit" }}
        >
          Decline
        </button>
        <button
          onClick={() => choose(true)}
          style={{ padding: "9px 18px", borderRadius: 9, border: "none", background: "linear-gradient(135deg, var(--pu-2563eb), var(--pu-0ea5e9))", color: "var(--pu-ffffff-t)", fontSize: 12.5, fontWeight: 800, cursor: "pointer", fontFamily: "inherit" }}
        >
          Accept
        </button>
      </div>
    </div>
  );
}

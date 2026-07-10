/**
 * Private admin console. The URL is intentionally not linked anywhere, but the
 * real protection is the backend ADMIN_EMAILS allowlist. This page also probes
 * the admin API before rendering the console so non-admin users never see the
 * operational UI shell.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router";
import { AdminPage } from "../components/dashboard/AdminPage";
import * as api from "../lib/api";

const F = "'Plus Jakarta Sans', sans-serif";
const T = {
  text: "var(--pu-f1f5f9-t)",
  t2: "var(--pu-226-232-240-072)",
  border: "var(--pu-148-163-184-008)",
  glass: "var(--pu-15-30-55-055)",
  red: "var(--pu-3b82f6-t)",
};

function PrivateMessage({ message }: { message: string }) {
  return (
    <div style={{ minHeight: "100vh", background: "var(--pu-0b1220)", padding: "32px 20px", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <div style={{ width: "100%", maxWidth: 520, borderRadius: 18, border: `1px solid ${T.border}`, background: T.glass, backdropFilter: "blur(20px)", padding: 28, textAlign: "center", fontFamily: F }}>
        <div style={{ color: T.text, fontSize: 20, fontWeight: 850, marginBottom: 8 }}>Private admin area</div>
        <div style={{ color: T.t2, fontSize: 13, lineHeight: 1.6, marginBottom: 18 }}>{message}</div>
        <Link to="/signin" style={{ color: T.red, fontSize: 13, fontWeight: 800 }}>Sign in with the admin account</Link>
      </div>
    </div>
  );
}

export default function AdminConsole() {
  const [allowed, setAllowed] = useState<null | boolean>(null);
  const [message, setMessage] = useState("Verifying admin access...");

  useEffect(() => {
    let active = true;
    api.getAdminSummary()
      .then(() => {
        if (active) setAllowed(true);
      })
      .catch((error) => {
        if (!active) return;
        setMessage((error as Error)?.message || "Admin access is required.");
        setAllowed(false);
      });
    return () => { active = false; };
  }, []);

  if (allowed !== true) {
    return <PrivateMessage message={allowed === null ? "Verifying admin access..." : message} />;
  }

  return (
    <div style={{ minHeight: "100vh", background: "var(--pu-0b1220)", padding: "clamp(18px, 3vw, 32px) clamp(12px, 2.5vw, 28px)" }}>
      <div style={{ maxWidth: 1440, margin: "0 auto", minWidth: 0 }}>
        <AdminPage />
      </div>
    </div>
  );
}

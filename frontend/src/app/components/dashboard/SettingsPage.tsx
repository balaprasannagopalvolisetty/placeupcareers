import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { motion } from "motion/react";
import { Save, AlertTriangle, MailCheck, KeyRound, Trash2 } from "lucide-react";
import * as api from "../../lib/api";
import { clearStoredToken } from "../../lib/api";

const F = { sans: "'Plus Jakarta Sans', sans-serif" };
const T = {
  text: "#F2EEB3", t2: "rgba(242,238,179,0.65)", t3: "rgba(242,238,179,0.45)",
  border: "rgba(242,238,179,0.08)", glass: "rgba(64,18,18,0.55)",
  grad: "linear-gradient(135deg, #8C3A27, #A6372D, #401212)", red: "#A6372D",
  input: "rgba(242,238,179,0.05)",
};

const JOB_PREFERENCE_SUGGESTIONS = [
  "Software Engineer",
  "Frontend Engineer",
  "Backend Engineer",
  "Full Stack Engineer",
  "Security Engineer",
  "Cybersecurity Analyst",
  "Data Engineer",
  "Machine Learning Engineer",
  "Data Scientist",
  "DevOps / Cloud Engineer",
  "Analytics Engineer",
  "Product Manager",
  "Business Analyst",
];

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ background: T.glass, backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 20, overflow: "hidden" }}>
      <div style={{ padding: "16px 24px", borderBottom: `1px solid ${T.border}` }}>
        <span style={{ fontFamily: F.sans, fontSize: 14, fontWeight: 600, color: T.text }}>{title}</span>
      </div>
      <div style={{ padding: 24 }}>{children}</div>
    </div>
  );
}

function Field({ label, type = "text", placeholder, value, onChange, disabled }: {
  label: string; type?: string; placeholder?: string; value: string;
  onChange?: (v: string) => void; disabled?: boolean;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
      <label style={{ fontSize: 12, fontWeight: 600, color: T.t2, fontFamily: F.sans }}>{label}</label>
      <input
        type={type}
        placeholder={placeholder}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange?.(e.target.value)}
        style={{ height: 44, padding: "0 14px", borderRadius: 10, border: `1px solid ${T.border}`, background: T.input, color: T.text, fontSize: 13, fontFamily: F.sans, outline: "none", opacity: disabled ? 0.6 : 1 }}
        onFocus={(e) => { e.target.style.borderColor = T.red; }}
        onBlur={(e) => { e.target.style.borderColor = T.border; }}
      />
    </div>
  );
}

function Toggle({ label, desc, on, onChange }: { label: string; desc: string; on: boolean; onChange: (v: boolean) => void }) {
  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 0", borderBottom: `1px solid ${T.border}` }}>
      <div>
        <div style={{ fontSize: 13, fontWeight: 500, color: T.text, fontFamily: F.sans }}>{label}</div>
        <div style={{ fontSize: 12, color: T.t3, fontFamily: F.sans, marginTop: 2 }}>{desc}</div>
      </div>
      <button onClick={() => onChange(!on)} style={{ width: 44, height: 24, borderRadius: 9999, border: "none", background: on ? T.grad : "rgba(242,238,179,0.1)", cursor: "pointer", position: "relative", transition: "background 0.25s", flexShrink: 0 }}>
        <div style={{ position: "absolute", top: 2, left: on ? 22 : 2, width: 20, height: 20, borderRadius: "50%", background: "#fff", transition: "left 0.25s", boxShadow: "0 1px 4px rgba(0,0,0,0.3)" }} />
      </button>
    </div>
  );
}

export function SettingsPage() {
  const [profile, setProfile] = useState<api.UserProfile | null>(null);
  const [prefs, setPrefs] = useState<api.UserPreferences | null>(null);
  const [pwCurrent, setPwCurrent] = useState("");
  const [pwNew, setPwNew] = useState("");
  const [pwConfirm, setPwConfirm] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Account-deletion confirmation flow — kept local to this page so a
  // misrouted state update somewhere else can't accidentally trigger it.
  const [deletePassword, setDeletePassword] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  // Forgot/verify status notes shown next to the email field.
  const [forgotStatus, setForgotStatus] = useState<string | null>(null);
  const [verifyStatus, setVerifyStatus] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    let active = true;
    Promise.all([api.getProfile(), api.getPreferences()])
      .then(([p, pr]) => { if (active) { setProfile(p); setPrefs(pr); } })
      .catch((err) => { if (active) setError((err as Error).message); });
    return () => { active = false; };
  }, []);

  const update = (k: keyof api.UserProfile, v: string) => setProfile((p) => p ? ({ ...p, [k]: v }) : p);
  const updatePref = (k: keyof api.UserPreferences, v: any) => setPrefs((pr) => pr ? ({ ...pr, [k]: v }) : pr);
  const rolesFromPreferenceText = (value: string) => value
    .split(/[,;\n]/)
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, 25);
  const addJobPreference = (suggestion: string) => {
    setPrefs((pr) => {
      if (!pr) return pr;
      const current = pr.job_preferences || "";
      const parts = current.split(",").map((item) => item.trim()).filter(Boolean);
      if (parts.some((item) => item.toLowerCase() === suggestion.toLowerCase())) return pr;
      const next = [...parts, suggestion];
      const targetRoles = Array.from(new Set([...(pr.target_roles || []), suggestion]));
      return { ...pr, job_preferences: next.join(", "), target_roles: targetRoles.slice(0, 25) };
    });
  };

  const handleSave = async () => {
    if (!profile || !prefs) return;
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      await api.updateProfile(profile);
      await api.updatePreferences({
        ...prefs,
        target_roles: rolesFromPreferenceText(prefs.job_preferences || "").length
          ? rolesFromPreferenceText(prefs.job_preferences || "")
          : (prefs.target_roles || []).slice(0, 25),
      });
      if (pwNew) {
        if (pwNew !== pwConfirm) throw new Error("Passwords don't match");
        if (pwNew.length < 8) throw new Error("Password must be ≥ 8 chars");
        await api.changePassword({ current_password: pwCurrent, new_password: pwNew });
        setPwCurrent(""); setPwNew(""); setPwConfirm("");
      }
      setSaved(true);
      setTimeout(() => setSaved(false), 2200);
    } catch (e) {
      setError((e as Error).message || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  if (!profile || !prefs) {
    return <div style={{ color: T.text, fontFamily: F.sans, padding: 40, textAlign: "center" }}>Loading settings...</div>;
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20, maxWidth: 720 }}>
      <Section title="Profile Information">
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
          <Field label="First Name" value={profile.first_name || ""} onChange={(v) => update("first_name", v)} />
          <Field label="Last Name" value={profile.last_name || ""} onChange={(v) => update("last_name", v)} />
          <Field label="Email" type="email" value={profile.email || ""} disabled />
          <Field label="Phone" type="tel" value={profile.phone || ""} onChange={(v) => update("phone", v)} />
        </div>
      </Section>

      <Section title="Career Preferences">
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
          <Field label="Current Visa Status" value={profile.visa_status || ""} onChange={(v) => update("visa_status", v)} />
          <Field label="Years of Experience" value={profile.experience_years || ""} onChange={(v) => update("experience_years", v)} />
        </div>
        <div style={{ marginTop: 14 }}>
          <label style={{ fontSize: 12, fontWeight: 600, color: T.t2, fontFamily: F.sans, display: "block", marginBottom: 5 }}>Job Preferences</label>
          <textarea
            value={prefs.job_preferences || ""}
            onChange={(e) => updatePref("job_preferences", e.target.value)}
            style={{ width: "100%", height: 80, padding: "10px 14px", borderRadius: 10, border: `1px solid ${T.border}`, background: T.input, color: T.text, fontSize: 13, fontFamily: F.sans, resize: "none", outline: "none", boxSizing: "border-box" }} />
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 10 }}>
            {JOB_PREFERENCE_SUGGESTIONS.map((suggestion) => {
              const selected = (prefs.job_preferences || "").toLowerCase().includes(suggestion.toLowerCase());
              return (
                <button key={suggestion} type="button" onClick={() => addJobPreference(suggestion)}
                  style={{ fontSize: 11, fontWeight: 600, padding: "5px 9px", borderRadius: 6, fontFamily: F.sans,
                    cursor: selected ? "default" : "pointer", background: selected ? "rgba(166,55,45,0.16)" : "rgba(242,238,179,0.05)",
                    color: selected ? T.red : T.t2, border: selected ? "1px solid rgba(166,55,45,0.28)" : `1px solid ${T.border}` }}>
                  {suggestion}
                </button>
              );
            })}
          </div>
        </div>
      </Section>

      <Section title="Notification Preferences">
        <Toggle label="New Job Matches" desc="Get notified when new jobs match your profile" on={prefs.notification_new_jobs} onChange={(v) => updatePref("notification_new_jobs", v)} />
        <Toggle label="Daily Digest" desc="Top 10 matches every morning at 9AM EST" on={prefs.notification_daily_digest} onChange={(v) => updatePref("notification_daily_digest", v)} />
        <Toggle label="ATS Score Updates" desc="Alerts when your score changes" on={prefs.notification_ats_updates} onChange={(v) => updatePref("notification_ats_updates", v)} />
        <Toggle label="Weekly Summary" desc="Performance report every Monday" on={prefs.notification_weekly_summary} onChange={(v) => updatePref("notification_weekly_summary", v)} />
        <Toggle label="Marketing Emails" desc="Product updates and tips" on={prefs.notification_marketing_emails} onChange={(v) => updatePref("notification_marketing_emails", v)} />
      </Section>

      <Section title="Email & Account">
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div style={{
            display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap",
            padding: "12px 14px", borderRadius: 10,
            background: (profile as any).email_verified ? "rgba(34,197,94,0.07)" : "rgba(242,238,179,0.04)",
            border: `1px solid ${(profile as any).email_verified ? "rgba(34,197,94,0.22)" : T.border}`,
          }}>
            <MailCheck size={16} color={(profile as any).email_verified ? "#22c55e" : T.t3} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13, color: T.text, fontFamily: F.sans, fontWeight: 600 }}>
                {profile.email || "—"}
              </div>
              <div style={{ fontSize: 11, color: T.t3, fontFamily: F.sans, marginTop: 2 }}>
                {(profile as any).email_verified
                  ? "Verified"
                  : "Not yet verified — verification helps recover your account."}
              </div>
            </div>
            {!(profile as any).email_verified && (
              <button
                onClick={async () => {
                  try {
                    const r = await api.resendVerification(profile.email || "");
                    setVerifyStatus(r.message || "Verification email re-sent — check your inbox.");
                  } catch (e) {
                    setVerifyStatus((e as Error).message || "Could not send verification right now.");
                  }
                }}
                style={{
                  padding: "8px 12px", borderRadius: 8, border: `1px solid ${T.border}`,
                  background: "rgba(242,238,179,0.05)", color: T.text,
                  fontSize: 12, fontFamily: F.sans, cursor: "pointer",
                }}
              >Resend verification</button>
            )}
          </div>
          {verifyStatus && (
            <div style={{ fontSize: 12, color: T.t2, fontFamily: F.sans, paddingLeft: 4 }}>{verifyStatus}</div>
          )}

          <div style={{ fontSize: 12, color: T.t3, fontFamily: F.sans, lineHeight: 1.5 }}>
            Your account data lives in encrypted Firestore collections
            (<code>users</code>, <code>user_preferences</code>, <code>user_resumes</code>,
            <code>user_applications</code>, <code>user_alerts</code>, <code>auth_sessions</code>).
            See <a href="/privacy" style={{ color: T.t2 }}>Privacy Policy</a> for the
            full breakdown.
          </div>
        </div>
      </Section>

      <Section title="Security">
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <Field label="Current Password" type="password" placeholder="••••••••" value={pwCurrent} onChange={setPwCurrent} />
          <Field label="New Password" type="password" placeholder="••••••••" value={pwNew} onChange={setPwNew} />
          <Field label="Confirm New Password" type="password" placeholder="••••••••" value={pwConfirm} onChange={setPwConfirm} />
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 4, flexWrap: "wrap" }}>
            <button
              type="button"
              onClick={async () => {
                if (!profile.email) return;
                try {
                  const r = await api.forgotPassword(profile.email);
                  setForgotStatus(r.message || "Reset link sent — check your inbox.");
                } catch (e) {
                  setForgotStatus((e as Error).message || "Couldn't send reset link.");
                }
              }}
              style={{
                display: "inline-flex", alignItems: "center", gap: 6,
                padding: "8px 12px", borderRadius: 8,
                border: `1px solid ${T.border}`, background: "transparent",
                color: T.t2, fontSize: 12, fontFamily: F.sans, cursor: "pointer",
              }}
            >
              <KeyRound size={12} /> Forgot password? Send reset link
            </button>
            {forgotStatus && (
              <span style={{ fontSize: 12, color: "#22c55e", fontFamily: F.sans }}>{forgotStatus}</span>
            )}
          </div>
        </div>
      </Section>

      <Section title="Danger Zone">
        <div style={{
          display: "flex", gap: 12, alignItems: "flex-start", flexWrap: "wrap",
          padding: 14, borderRadius: 10,
          background: "rgba(166,55,45,0.06)", border: "1px solid rgba(166,55,45,0.25)",
        }}>
          <AlertTriangle size={18} color={T.red} style={{ marginTop: 2 }} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: T.text, fontFamily: F.sans }}>
              Delete your account
            </div>
            <div style={{ fontSize: 12, color: T.t2, fontFamily: F.sans, marginTop: 4, lineHeight: 1.5 }}>
              Permanently removes your profile, resumes, applications, alerts, and saved jobs.
              This cannot be undone. Backups roll off within 30 days.
            </div>
          </div>
          <button
            onClick={() => { setDeletePassword(""); setDeleteError(null); setShowDeleteModal(true); }}
            style={{
              display: "inline-flex", alignItems: "center", gap: 6,
              padding: "9px 14px", borderRadius: 9,
              border: "1px solid rgba(166,55,45,0.4)", background: "rgba(166,55,45,0.12)",
              color: T.red, fontSize: 12, fontWeight: 600, fontFamily: F.sans, cursor: "pointer",
            }}
          >
            <Trash2 size={13} /> Delete account
          </button>
        </div>
      </Section>

      {showDeleteModal && (
        <div
          role="dialog"
          aria-modal="true"
          onClick={() => !deleting && setShowDeleteModal(false)}
          style={{
            position: "fixed", inset: 0, zIndex: 200,
            background: "rgba(1,17,38,0.85)", backdropFilter: "blur(6px)",
            display: "flex", alignItems: "center", justifyContent: "center", padding: 20,
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              width: "min(440px, 100%)", padding: "28px 26px", borderRadius: 18,
              background: "rgba(64,18,18,0.92)", border: "1px solid rgba(242,238,179,0.1)",
              color: T.text, fontFamily: F.sans,
            }}
          >
            <h3 style={{ fontSize: 17, fontWeight: 700, margin: 0 }}>Delete your account?</h3>
            <p style={{ fontSize: 13, color: T.t2, lineHeight: 1.5, marginTop: 8 }}>
              Type your password to confirm. Every Firestore record we hold for you will be
              removed immediately. Your refresh tokens will be revoked so all other devices
              are signed out.
            </p>
            <input
              type="password"
              autoComplete="current-password"
              placeholder="Password (or type DELETE if you signed in with Google)"
              value={deletePassword}
              onChange={(e) => setDeletePassword(e.target.value)}
              style={{
                width: "100%", boxSizing: "border-box",
                height: 42, padding: "0 12px", marginTop: 14, borderRadius: 10,
                border: `1px solid ${T.border}`, background: T.input,
                color: T.text, fontSize: 13, fontFamily: F.sans, outline: "none",
              }}
            />
            {deleteError && (
              <div style={{ marginTop: 10, color: T.red, fontSize: 12 }}>{deleteError}</div>
            )}
            <div style={{ display: "flex", gap: 10, marginTop: 18, justifyContent: "flex-end" }}>
              <button
                disabled={deleting}
                onClick={() => setShowDeleteModal(false)}
                style={{
                  padding: "9px 14px", borderRadius: 9,
                  border: `1px solid ${T.border}`, background: "transparent",
                  color: T.t2, fontSize: 13, fontFamily: F.sans, cursor: "pointer",
                }}
              >Cancel</button>
              <button
                disabled={deleting || !deletePassword}
                onClick={async () => {
                  setDeleting(true);
                  setDeleteError(null);
                  try {
                    await api.deleteAccount(deletePassword);
                    clearStoredToken();
                    navigate("/", { replace: true });
                  } catch (e) {
                    setDeleteError((e as Error).message || "Delete failed");
                  } finally {
                    setDeleting(false);
                  }
                }}
                style={{
                  padding: "9px 14px", borderRadius: 9, border: "none",
                  background: "linear-gradient(135deg, #8C3A27, #A6372D, #401212)",
                  color: "#fff", fontSize: 13, fontWeight: 600, fontFamily: F.sans,
                  cursor: deleting || !deletePassword ? "not-allowed" : "pointer",
                  opacity: deleting || !deletePassword ? 0.6 : 1,
                }}
              >
                {deleting ? "Deleting…" : "Yes, delete forever"}
              </button>
            </div>
          </div>
        </div>
      )}

      {error ? (
        <div style={{ color: "#ef4444", fontFamily: F.sans, fontSize: 13 }}>{error}</div>
      ) : null}

      <motion.button whileTap={{ scale: 0.97 }} onClick={handleSave} disabled={saving}
        style={{ display: "flex", alignItems: "center", gap: 8, padding: "13px 28px", borderRadius: 12, border: "none", background: saved ? "rgba(34,197,94,0.9)" : T.grad, color: "#fff", fontSize: 14, fontWeight: 600, fontFamily: F.sans, cursor: saving ? "wait" : "pointer", width: "fit-content", boxShadow: "0 0 20px rgba(166,55,45,0.3)", transition: "background 0.3s" }}>
        <Save size={15} /> {saving ? "Saving…" : saved ? "Saved!" : "Save Changes"}
      </motion.button>
    </div>
  );
}

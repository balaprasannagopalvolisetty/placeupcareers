import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { Save } from "lucide-react";
import * as api from "../../lib/api";

const F = { sans: "'Plus Jakarta Sans', sans-serif" };
const T = {
  text: "#F2EEB3", t2: "rgba(242,238,179,0.65)", t3: "rgba(242,238,179,0.45)",
  border: "rgba(242,238,179,0.08)", glass: "rgba(64,18,18,0.55)",
  grad: "linear-gradient(135deg, #8C3A27, #A6372D, #401212)", red: "#A6372D",
  input: "rgba(242,238,179,0.05)",
};

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

  useEffect(() => {
    let active = true;
    Promise.all([api.getProfile(), api.getPreferences()])
      .then(([p, pr]) => { if (active) { setProfile(p); setPrefs(pr); } })
      .catch((err) => { if (active) setError((err as Error).message); });
    return () => { active = false; };
  }, []);

  const update = (k: keyof api.UserProfile, v: string) => setProfile((p) => p ? ({ ...p, [k]: v }) : p);
  const updatePref = (k: keyof api.UserPreferences, v: any) => setPrefs((pr) => pr ? ({ ...pr, [k]: v }) : pr);

  const handleSave = async () => {
    if (!profile || !prefs) return;
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      await api.updateProfile(profile);
      await api.updatePreferences(prefs);
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
        </div>
      </Section>

      <Section title="Notification Preferences">
        <Toggle label="New Job Matches" desc="Get notified when new jobs match your profile" on={prefs.notification_new_jobs} onChange={(v) => updatePref("notification_new_jobs", v)} />
        <Toggle label="Daily Digest" desc="Top 10 matches every morning at 9AM EST" on={prefs.notification_daily_digest} onChange={(v) => updatePref("notification_daily_digest", v)} />
        <Toggle label="ATS Score Updates" desc="Alerts when your score changes" on={prefs.notification_ats_updates} onChange={(v) => updatePref("notification_ats_updates", v)} />
        <Toggle label="Weekly Summary" desc="Performance report every Monday" on={prefs.notification_weekly_summary} onChange={(v) => updatePref("notification_weekly_summary", v)} />
        <Toggle label="Marketing Emails" desc="Product updates and tips" on={prefs.notification_marketing_emails} onChange={(v) => updatePref("notification_marketing_emails", v)} />
      </Section>

      <Section title="Security">
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <Field label="Current Password" type="password" placeholder="••••••••" value={pwCurrent} onChange={setPwCurrent} />
          <Field label="New Password" type="password" placeholder="••••••••" value={pwNew} onChange={setPwNew} />
          <Field label="Confirm New Password" type="password" placeholder="••••••••" value={pwConfirm} onChange={setPwConfirm} />
        </div>
      </Section>

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

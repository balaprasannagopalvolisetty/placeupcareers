import { useState, useEffect } from "react";
import { motion } from "motion/react";
import { Bell, BellOff, Trash2, MapPin, DollarSign, Check } from "lucide-react";
import * as api from "../../lib/api";

const F = { sans: "'Plus Jakarta Sans', sans-serif" };
const T = {
  text: "#F2EEB3", t2: "rgba(242,238,179,0.65)", t3: "rgba(242,238,179,0.45)",
  border: "rgba(242,238,179,0.08)", glass: "rgba(64,18,18,0.55)",
  grad: "linear-gradient(135deg, #8C3A27, #A6372D, #401212)", red: "#A6372D",
};

export function AlertsPage() {
  const [alerts, setAlerts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [enabled, setEnabled] = useState({ email: true, daily: true, weekly: false });

  useEffect(() => {
    let active = true;
    setLoading(true);
    
    Promise.all([
      api.getAlerts().then(data => {
        if (active) setAlerts(Array.isArray(data) ? data : data.alerts || []);
      }).catch(() => {
        if (active) setAlerts([]);
      }),
      api.getAlertSettings().then(data => {
        if (active && data) {
          setEnabled({
            email: data.email_alerts !== false,
            daily: data.daily_digest !== false,
            weekly: (data as any).weekly_report ?? (data as any).weekly_digest ?? false,
          });
        }
      }).catch(() => {}),
    ]).finally(() => {
      if (active) setLoading(false);
    });

    return () => { active = false; };
  }, []);

  const handleToggleSetting = async (key: 'email' | 'daily' | 'weekly', value: boolean) => {
    setEnabled(e => ({ ...e, [key]: value }));
    try {
      await api.updateAlertSettings({
        email_alerts: key === 'email' ? value : enabled.email,
        daily_digest: key === 'daily' ? value : enabled.daily,
        weekly_report: key === 'weekly' ? value : enabled.weekly,
      });
    } catch (err) {
      console.error('Failed to update alert settings:', err);
      setEnabled(e => ({ ...e, [key]: !value }));
    }
  };

  const handleMarkRead = async (alertId: number | string) => {
    try {
      await api.markAlertRead(String(alertId));
      setAlerts(a => a.map(x => x.id === alertId ? { ...x, unread: false } : x));
    } catch (err) {
      console.error('Failed to mark alert read:', err);
    }
  };

  const handleMarkAllRead = async () => {
    try {
      await api.markAllAlertsRead();
      setAlerts(a => a.map(x => ({ ...x, unread: false })));
    } catch (err) {
      console.error('Failed to mark all alerts read:', err);
    }
  };

  const handleDeleteAlert = async (alertId: number | string) => {
    try {
      await api.deleteAlert(String(alertId));
      setAlerts(a => a.filter(x => x.id !== alertId));
    } catch (err) {
      console.error('Failed to delete alert:', err);
    }
  };

  if (loading) {
    return <div style={{ color: T.text, fontFamily: F.sans, textAlign: 'center', padding: 40 }}>Loading alerts...</div>;
  }

  const displayAlerts = Array.isArray(alerts) ? alerts : [];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      {/* Settings */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 14 }}>
        {[
          { key: "email", label: "Email Alerts", desc: "Instant match notifications" },
          { key: "daily", label: "Daily Digest", desc: "Top 10 matches at 9AM EST" },
          { key: "weekly", label: "Weekly Report", desc: "Summary every Monday" },
        ].map((item) => (
          <div key={item.key} style={{ background: T.glass, backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 16, padding: "18px 20px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div>
              <div style={{ fontSize: 14, fontWeight: 600, color: T.text, fontFamily: F.sans, marginBottom: 2 }}>{item.label}</div>
              <div style={{ fontSize: 12, color: T.t3, fontFamily: F.sans }}>{item.desc}</div>
            </div>
            <button
              onClick={() => handleToggleSetting(item.key as 'email' | 'daily' | 'weekly', !enabled[item.key as keyof typeof enabled])}
              style={{ width: 44, height: 24, borderRadius: 9999, border: "none", background: enabled[item.key as keyof typeof enabled] ? T.grad : "rgba(242,238,179,0.1)", cursor: "pointer", position: "relative", transition: "background 0.25s", flexShrink: 0 }}
            >
              <div style={{ position: "absolute", top: 2, left: enabled[item.key as keyof typeof enabled] ? 22 : 2, width: 20, height: 20, borderRadius: "50%", background: "#fff", transition: "left 0.25s", boxShadow: "0 1px 4px rgba(0,0,0,0.3)" }} />
            </button>
          </div>
        ))}
      </div>

      {/* Alert feed */}
      <div style={{ background: T.glass, backdropFilter: "blur(20px)", border: `1px solid ${T.border}`, borderRadius: 20, overflow: "hidden" }}>
        <div style={{ padding: "18px 24px", borderBottom: `1px solid ${T.border}`, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ fontFamily: F.sans, fontSize: 15, fontWeight: 600, color: T.text }}>Recent Alerts <span style={{ fontSize: 12, color: T.red, fontWeight: 700, marginLeft: 6 }}>{displayAlerts.filter((a) => a.unread).length} new</span></div>
          <button onClick={handleMarkAllRead} style={{ fontSize: 12, color: T.red, fontFamily: F.sans, background: "none", border: "none", cursor: "pointer", fontWeight: 600 }}>Mark all read</button>
        </div>
        {displayAlerts.length === 0 ? (
          <div style={{ padding: "40px", textAlign: "center", color: T.t3 }}>No alerts yet. Your job matches will appear here.</div>
        ) : (
          displayAlerts.map((alert, i) => (
            <motion.div key={alert.id} initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.06 }}
              style={{ display: "flex", alignItems: "center", gap: 14, padding: "16px 24px", borderBottom: i < displayAlerts.length - 1 ? `1px solid ${T.border}` : "none", background: alert.unread ? "rgba(166,55,45,0.04)" : "transparent", cursor: "pointer" }}
              onClick={() => alert.unread && handleMarkRead(alert.id)}>
              <div style={{ width: 40, height: 40, borderRadius: "50%", background: alert.match_score ? T.grad : "rgba(242,238,179,0.08)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                {alert.match_score ? <Bell size={16} color="#fff" /> : <Check size={16} color={T.red} />}
              </div>
              {alert.unread && <div style={{ width: 6, height: 6, borderRadius: "50%", background: T.red, boxShadow: `0 0 6px ${T.red}`, flexShrink: 0 }} />}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 14, fontWeight: 600, color: T.text, fontFamily: F.sans, marginBottom: 2 }}>{alert.title || alert.message}</div>
                <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
                  {alert.company && (
                    <>
                      <span style={{ fontSize: 12, color: T.t2, fontFamily: F.sans }}>{alert.company}</span>
                      {alert.location && <span style={{ display: "flex", alignItems: "center", gap: 3, fontSize: 12, color: T.t3, fontFamily: F.sans }}><MapPin size={10} />{alert.location}</span>}
                      {alert.salary && <span style={{ display: "flex", alignItems: "center", gap: 3, fontSize: 12, color: T.t3, fontFamily: F.sans }}><DollarSign size={10} />{alert.salary}</span>}
                    </>
                  )}
                </div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 10, flexShrink: 0 }}>
                {alert.match_score && <span style={{ fontSize: 13, fontWeight: 700, color: T.red, fontFamily: F.sans }}>{alert.match_score}%</span>}
                <span style={{ fontSize: 12, color: T.t3, fontFamily: F.sans }}>{alert.created_at ? new Date(alert.created_at).toLocaleDateString() : 'Recently'}</span>
                <button onClick={(e) => { e.stopPropagation(); handleDeleteAlert(alert.id); }} style={{ background: "none", border: "none", cursor: "pointer", color: T.t3 }}>
                  <Trash2 size={14} />
                </button>
              </div>
            </motion.div>
          ))
   
     )}
      </div>
    </div>
  );
}

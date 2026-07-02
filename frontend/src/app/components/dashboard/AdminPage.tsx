import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { Activity, Check, Database, Globe, ListChecks, Loader2, Lock, Mail, RefreshCw, Shield, Upload, Users, WalletCards, X } from "lucide-react";
import * as api from "../../lib/api";

const F = { sans: "'Plus Jakarta Sans', sans-serif", mono: "'JetBrains Mono', monospace" };
const T = {
  text: "#F1F5F9",
  t2: "rgba(226,232,240,0.72)",
  t3: "rgba(148,163,184,0.75)",
  border: "rgba(148,163,184,0.08)",
  glass: "rgba(15,30,55,0.55)",
  grad: "linear-gradient(135deg, #2563EB, #0EA5E9)",
  red: "#3B82F6",
};

function Panel({ children }: { children: React.ReactNode }) {
  return (
    <div style={{ borderRadius: 18, border: `1px solid ${T.border}`, background: T.glass, backdropFilter: "blur(20px)", overflow: "hidden" }}>
      {children}
    </div>
  );
}

function messageFromError(err: unknown, fallback: string) {
  return err instanceof Error && err.message ? err.message : fallback;
}

function isAuthError(message: string) {
  return /admin access|admin authorization|unauthorized|forbidden|not authenticated|401|403/i.test(message);
}

function withTimeout<T>(promise: Promise<T>, ms: number, label: string) {
  let timer: ReturnType<typeof setTimeout>;
  const timeout = new Promise<T>((_, reject) => {
    timer = setTimeout(() => reject(new Error(`${label} timed out`)), ms);
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

export function AdminPage() {
  const [summary, setSummary] = useState<api.AdminSummary | null>(null);
  const [users, setUsers] = useState<Array<Record<string, unknown>>>([]);
  const [usersLoading, setUsersLoading] = useState(true);
  const [usersError, setUsersError] = useState("");
  const [paymentsNote, setPaymentsNote] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState("");
  const [roleRequests, setRoleRequests] = useState<api.RoleRequest[]>([]);
  const [roleRequestsError, setRoleRequestsError] = useState("");
  const [coverage, setCoverage] = useState<{ total_positions: number; per_country: api.CoverageCountry[]; top_roles?: Array<{ role: string; count: number }> } | null>(null);
  const [coverageLoading, setCoverageLoading] = useState(false);
  const [coverageError, setCoverageError] = useState("");
  const [openCountry, setOpenCountry] = useState<string | null>(null);
  const [events, setEvents] = useState<Array<Record<string, unknown>>>([]);
  const [eventsLoading, setEventsLoading] = useState(false);
  const [eventsError, setEventsError] = useState("");
  const [detail, setDetail] = useState<Record<string, unknown> | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailMsg, setDetailMsg] = useState("");

  const loadRoleRequests = () => {
    setRoleRequestsError("");
    api.getAdminRoleRequests()
      .then((r) => setRoleRequests(r.requests || []))
      .catch((err) => setRoleRequestsError(messageFromError(err, "Could not load role requests.")));
  };

  const loadCoverage = () => {
    setCoverageLoading(true);
    setCoverageError("");
    withTimeout(api.getAdminCoverage(), 12000, "Coverage request")
      .then(setCoverage)
      .catch((err) => setCoverageError(messageFromError(err, "Coverage is taking too long to load.")))
      .finally(() => setCoverageLoading(false));
  };

  useEffect(() => {
    api.getAdminSummary()
      .then(setSummary)
      .catch((err) => setError(messageFromError(err, "Admin access required.")));
    api.getAdminUsers(500)
      .then((res) => {
        setUsers(res.users || []);
        setUsersError("");
      })
      .catch((err) => {
        const message = messageFromError(err, "Could not load user accounts.");
        setUsersError(message);
        if (isAuthError(message)) setError(message);
      })
      .finally(() => setUsersLoading(false));
    api.getAdminPayments()
      .then((res) => setPaymentsNote(res.note || ""))
      .catch(() => {});
    loadRoleRequests();
    setEventsLoading(true);
    withTimeout(api.getAdminEvents({ limit: 40 }), 7000, "Activity request")
      .then((r) => {
        setEvents(r.events || []);
        setEventsError("");
      })
      .catch((err) => setEventsError(messageFromError(err, "Activity log is taking too long to load.")))
      .finally(() => setEventsLoading(false));
  }, []);

  const decide = async (id: string, decision: "approved" | "rejected") => {
    try {
      await api.decideRoleRequest(id, decision);
      loadRoleRequests();
    } catch (err) {
      setError((err as Error)?.message || "Could not update request");
    }
  };

  const pendingRequests = roleRequests.filter((r) => r.status === "pending");
  const maxPositions = Math.max(1, ...(coverage?.per_country || []).map((c) => c.positions));
  const topRoles = coverage?.top_roles || [];
  const maxRolePositions = Math.max(1, ...topRoles.map((r) => r.count));

  const openUser = async (id: string) => {
    setDetail(null);
    setDetailMsg("");
    setDetailLoading(true);
    try {
      const d = await api.getAdminUserDetail(id);
      setDetail(d);
    } catch (err) {
      setDetailMsg((err as Error)?.message || "Could not load user");
      setDetail({ error: true } as Record<string, unknown>);
    } finally {
      setDetailLoading(false);
    }
  };

  const detailUserId = () => {
    const u = (detail?.user as Record<string, unknown>) || {};
    return String(u.id || "");
  };

  const triggerReset = async () => {
    const id = detailUserId();
    if (!id) return;
    setDetailMsg("");
    try {
      const r = await api.adminTriggerPasswordReset(id);
      setDetailMsg(`Password-reset email sent to ${r.email}.`);
    } catch (err) {
      setDetailMsg((err as Error)?.message || "Could not send reset");
    }
  };

  const revoke = async () => {
    const id = detailUserId();
    if (!id) return;
    setDetailMsg("");
    try {
      const r = await api.adminRevokeSessions(id);
      setDetailMsg(`Revoked ${r.revoked} session(s) — user is signed out everywhere.`);
    } catch (err) {
      setDetailMsg((err as Error)?.message || "Could not revoke sessions");
    }
  };

  const uploadCsv = async (dryRun: boolean) => {
    if (!file) {
      setError("Choose a LinkedIn profile CSV first.");
      return;
    }
    setUploading(true);
    setError("");
    setResult(null);
    try {
      const response = await api.uploadAdminFinalScoutCsv(file, { limit: 500, concurrency: 4, dry_run: dryRun });
      setResult(response);
    } catch (err) {
      setError((err as Error)?.message || "CSV enrichment failed");
    } finally {
      setUploading(false);
    }
  };

  if (error && !summary) {
    return (
      <Panel>
        <div style={{ padding: 28, textAlign: "center", color: T.t2, fontFamily: F.sans }}>
          <Lock size={26} color={T.red} />
          <div style={{ color: T.text, fontSize: 18, fontWeight: 800, marginTop: 10 }}>Private admin area</div>
          <div style={{ fontSize: 13, marginTop: 6 }}>{error}</div>
        </div>
      </Panel>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18, fontFamily: F.sans }}>
      <div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, color: T.red, fontSize: 12, fontWeight: 800, letterSpacing: "0.08em", textTransform: "uppercase" }}>
          <Shield size={15} /> Private Admin
        </div>
        <h2 style={{ color: T.text, fontSize: 24, fontWeight: 800, marginTop: 6, marginBottom: 4 }}>Users, access, and email extraction</h2>
        <p style={{ color: T.t2, fontSize: 13, lineHeight: 1.6, maxWidth: 760 }}>
          This route is hidden from normal navigation and protected by backend admin authorization.
        </p>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12 }}>
        {[
          { icon: Users, label: "User accounts", value: summary?.users ?? 0 },
          { icon: WalletCards, label: "Free access", value: "Enabled" },
          { icon: Mail, label: "FinalScout keys", value: summary?.finalscout.multi_key_configured ? "Configured" : "Missing" },
          { icon: ListChecks, label: "Pending role requests", value: pendingRequests.length },
          { icon: Globe, label: "Positions tracked", value: coverageLoading ? "Loading" : coverage?.total_positions ?? "Load" },
        ].map((item) => (
          <motion.div key={item.label} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} style={{ borderRadius: 16, border: `1px solid ${T.border}`, background: T.glass, padding: 16 }}>
            <item.icon size={17} color={T.red} />
            <div style={{ color: T.text, fontSize: 24, fontWeight: 900, marginTop: 10 }}>{item.value}</div>
            <div style={{ color: T.t3, fontSize: 12 }}>{item.label}</div>
          </motion.div>
        ))}
      </div>

      {/* Role request approvals */}
      <Panel>
        <div style={{ padding: 18, borderBottom: `1px solid ${T.border}`, display: "flex", alignItems: "center", gap: 10 }}>
          <ListChecks size={17} color={T.red} />
          <div>
            <div style={{ color: T.text, fontSize: 15, fontWeight: 800 }}>Role requests</div>
            <div style={{ color: T.t3, fontSize: 12 }}>Approve to flag for coverage, or reject with a note.</div>
          </div>
        </div>
        <div style={{ padding: 18 }}>
          {roleRequests.length === 0 ? (
            <div style={{ color: roleRequestsError ? T.red : T.t3, fontSize: 13 }}>{roleRequestsError || "No role requests yet."}</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {roleRequests.slice(0, 50).map((r) => (
                <div key={r.id} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12, padding: "10px 12px", borderRadius: 12, border: `1px solid ${T.border}`, background: "rgba(1,17,38,0.4)" }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ color: T.text, fontSize: 13, fontWeight: 700 }}>{r.role}{r.country ? ` · ${r.country}` : ""}</div>
                    <div style={{ color: T.t3, fontSize: 11 }}>{r.email}{r.note ? ` — ${r.note}` : ""}</div>
                  </div>
                  {r.status === "pending" ? (
                    <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
                      <button onClick={() => decide(r.id, "approved")} style={{ display: "flex", alignItems: "center", gap: 5, height: 32, padding: "0 12px", borderRadius: 8, border: "none", background: "rgba(34,197,94,0.15)", color: "#22c55e", fontSize: 12, fontWeight: 700, cursor: "pointer" }}><Check size={13} /> Approve</button>
                      <button onClick={() => decide(r.id, "rejected")} style={{ display: "flex", alignItems: "center", gap: 5, height: 32, padding: "0 12px", borderRadius: 8, border: "none", background: "rgba(239,68,68,0.15)", color: "#f87171", fontSize: 12, fontWeight: 700, cursor: "pointer" }}><X size={13} /> Reject</button>
                    </div>
                  ) : (
                    <span style={{ flexShrink: 0, fontSize: 11, fontWeight: 700, padding: "3px 10px", borderRadius: 9999, background: r.status === "approved" ? "rgba(34,197,94,0.12)" : "rgba(239,68,68,0.12)", color: r.status === "approved" ? "#22c55e" : "#f87171" }}>{r.status}</span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </Panel>

      {/* Scraper coverage per country */}
      <Panel>
        <div style={{ padding: 18, borderBottom: `1px solid ${T.border}`, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <Globe size={17} color={T.red} />
            <div>
              <div style={{ color: T.text, fontSize: 15, fontWeight: 800 }}>Scraper coverage - positions per country</div>
              <div style={{ color: T.t3, fontSize: 12 }}>
                {coverage ? `${coverage.total_positions.toLocaleString()} active positions in the database.` : "Load this only when needed; it is heavier than the user list."}
              </div>
            </div>
          </div>
          <button
            onClick={loadCoverage}
            disabled={coverageLoading}
            style={{ height: 34, padding: "0 12px", borderRadius: 9, border: `1px solid ${T.border}`, background: "rgba(148,163,184,0.05)", color: T.text, cursor: coverageLoading ? "wait" : "pointer", fontSize: 12, fontWeight: 800, display: "flex", alignItems: "center", gap: 7, flexShrink: 0 }}
          >
            <RefreshCw size={13} className={coverageLoading ? "animate-spin" : ""} />
            {coverage ? "Refresh" : "Load coverage"}
          </button>
        </div>
        <div style={{ padding: 18, display: "flex", flexDirection: "column", gap: 8 }}>
          {coverageLoading && <div style={{ color: T.t2, fontSize: 13 }}>Loading coverage snapshot...</div>}
          {coverageError && <div style={{ color: T.red, fontSize: 12 }}>{coverageError}. User accounts are still available below.</div>}
          {!coverageLoading && !coverageError && !coverage && <div style={{ color: T.t3, fontSize: 13 }}>Click Load coverage to fetch position counts without blocking the admin user table.</div>}
          {coverage && coverage.per_country.length === 0 && <div style={{ color: T.t3, fontSize: 13 }}>No position coverage returned yet.</div>}
          {topRoles.length > 0 && (
            <div style={{ padding: 12, borderRadius: 14, border: `1px solid ${T.border}`, background: "rgba(1,17,38,0.35)", marginBottom: 8 }}>
              <div style={{ color: T.text, fontSize: 13, fontWeight: 800, marginBottom: 8 }}>Top roles collected globally</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
                {topRoles.map((r) => (
                  <div key={r.role} style={{ display: "grid", gridTemplateColumns: "minmax(120px, 210px) 1fr 70px", alignItems: "center", gap: 10 }}>
                    <div style={{ color: T.t2, fontSize: 12, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{r.role}</div>
                    <div style={{ height: 12, borderRadius: 9999, background: "rgba(148,163,184,0.06)", overflow: "hidden" }}>
                      <div style={{ width: `${Math.round((r.count / maxRolePositions) * 100)}%`, height: "100%", background: T.grad }} />
                    </div>
                    <div style={{ color: T.text, fontSize: 12, fontWeight: 800, textAlign: "right" }}>{r.count.toLocaleString()}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
          {coverage && coverage.per_country.length > 0 && (
            <>
              <div style={{ color: T.t3, fontSize: 11, marginBottom: 2 }}>Click a country to see the roles the scraper has collected there.</div>
              {coverage.per_country.map((c) => {
                const expanded = openCountry === c.country;
                const roles = c.top_roles || [];
                return (
                  <div key={c.country}>
                    <div
                      onClick={() => setOpenCountry(expanded ? null : c.country)}
                      style={{ display: "flex", alignItems: "center", gap: 10, cursor: roles.length ? "pointer" : "default" }}>
                      <div style={{ width: 150, color: expanded ? T.text : T.t2, fontSize: 12, flexShrink: 0, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", fontWeight: expanded ? 700 : 400 }}>
                        {roles.length ? (expanded ? "v " : "> ") : ""}{c.country_name || c.country}
                      </div>
                      <div style={{ flex: 1, height: 14, borderRadius: 7, background: "rgba(148,163,184,0.06)", overflow: "hidden" }}>
                        <div style={{ width: `${Math.round((c.positions / maxPositions) * 100)}%`, height: "100%", background: T.grad }} />
                      </div>
                      <div style={{ width: 70, textAlign: "right", color: T.text, fontSize: 12, fontWeight: 700 }}>{c.positions.toLocaleString()}</div>
                    </div>
                    {expanded && roles.length > 0 && (
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, margin: "8px 0 4px 160px" }}>
                        {roles.map((r) => (
                          <span key={r.role} style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 11, color: T.t2, background: "rgba(1,17,38,0.5)", border: `1px solid ${T.border}`, borderRadius: 9999, padding: "3px 10px" }}>
                            {r.role}
                            <span style={{ color: T.red, fontWeight: 700 }}>{r.count.toLocaleString()}</span>
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </>
          )}
        </div>
      </Panel>

      {false && coverage && coverage.per_country.length > 0 && (
        <Panel>
          <div style={{ padding: 18, borderBottom: `1px solid ${T.border}`, display: "flex", alignItems: "center", gap: 10 }}>
            <Globe size={17} color={T.red} />
            <div>
              <div style={{ color: T.text, fontSize: 15, fontWeight: 800 }}>Scraper coverage — positions per country</div>
              <div style={{ color: T.t3, fontSize: 12 }}>{coverage.total_positions.toLocaleString()} active positions in the database.</div>
            </div>
          </div>
          <div style={{ padding: 18, display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ color: T.t3, fontSize: 11, marginBottom: 2 }}>Click a country to see the roles the scraper has collected there.</div>
            {coverage.per_country.map((c) => {
              const expanded = openCountry === c.country;
              const roles = c.top_roles || [];
              return (
                <div key={c.country}>
                  <div
                    onClick={() => setOpenCountry(expanded ? null : c.country)}
                    style={{ display: "flex", alignItems: "center", gap: 10, cursor: roles.length ? "pointer" : "default" }}>
                    <div style={{ width: 150, color: expanded ? T.text : T.t2, fontSize: 12, flexShrink: 0, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", fontWeight: expanded ? 700 : 400 }}>
                      {roles.length ? (expanded ? "▾ " : "▸ ") : ""}{c.country}
                    </div>
                    <div style={{ flex: 1, height: 14, borderRadius: 7, background: "rgba(148,163,184,0.06)", overflow: "hidden" }}>
                      <div style={{ width: `${Math.round((c.positions / maxPositions) * 100)}%`, height: "100%", background: T.grad }} />
                    </div>
                    <div style={{ width: 70, textAlign: "right", color: T.text, fontSize: 12, fontWeight: 700 }}>{c.positions.toLocaleString()}</div>
                  </div>
                  {expanded && roles.length > 0 && (
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6, margin: "8px 0 4px 160px" }}>
                      {roles.map((r) => (
                        <span key={r.role} style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 11, color: T.t2, background: "rgba(1,17,38,0.5)", border: `1px solid ${T.border}`, borderRadius: 9999, padding: "3px 10px" }}>
                          {r.role}
                          <span style={{ color: T.red, fontWeight: 700 }}>{r.count.toLocaleString()}</span>
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </Panel>
      )}

      <Panel>
        <div style={{ padding: 18, borderBottom: `1px solid ${T.border}`, display: "flex", alignItems: "center", gap: 10 }}>
          <Upload size={17} color={T.red} />
          <div>
            <div style={{ color: T.text, fontSize: 15, fontWeight: 800 }}>LinkedIn CSV to email extraction</div>
            <div style={{ color: T.t3, fontSize: 12 }}>CSV columns: linkedin_url or first_name, last_name, company.</div>
          </div>
        </div>
        <div style={{ padding: 18, display: "flex", flexDirection: "column", gap: 12 }}>
          <input
            type="file"
            accept=".csv,text/csv"
            onChange={(event) => setFile(event.target.files?.[0] || null)}
            style={{ color: T.t2, fontSize: 13 }}
          />
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button onClick={() => uploadCsv(true)} disabled={uploading} style={{ height: 38, padding: "0 14px", borderRadius: 10, border: `1px solid ${T.border}`, background: "rgba(148,163,184,0.05)", color: T.text, cursor: uploading ? "wait" : "pointer", fontSize: 12, fontWeight: 800 }}>
              Dry run
            </button>
            <button onClick={() => uploadCsv(false)} disabled={uploading} style={{ height: 38, padding: "0 14px", borderRadius: 10, border: "none", background: T.grad, color: "#fff", cursor: uploading ? "wait" : "pointer", fontSize: 12, fontWeight: 800, display: "flex", alignItems: "center", gap: 8 }}>
              {uploading && <Loader2 size={14} className="animate-spin" />}
              Extract emails
            </button>
          </div>
          {error && <div style={{ color: T.red, fontSize: 12 }}>{error}</div>}
          {result && (
            <pre style={{ margin: 0, padding: 12, borderRadius: 12, background: "rgba(1,17,38,0.55)", border: `1px solid ${T.border}`, color: T.t2, fontSize: 11, fontFamily: F.mono, overflowX: "auto" }}>
              {JSON.stringify(result, null, 2)}
            </pre>
          )}
        </div>
      </Panel>

      <Panel>
        <div style={{ padding: 18, borderBottom: `1px solid ${T.border}`, display: "flex", alignItems: "center", gap: 10 }}>
          <Database size={17} color={T.red} />
          <div style={{ color: T.text, fontSize: 15, fontWeight: 800 }}>User accounts</div>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", color: T.t2, fontSize: 12 }}>
            <thead>
              <tr style={{ color: T.t3, borderBottom: `1px solid ${T.border}` }}>
                {["Name", "Email", "Plan", "Visa", "Created"].map((label) => <th key={label} style={{ textAlign: "left", padding: 12, fontWeight: 700 }}>{label}</th>)}
              </tr>
            </thead>
            <tbody>
              {usersLoading && (
                <tr>
                  <td colSpan={5} style={{ padding: 16, color: T.t3 }}>Loading user accounts...</td>
                </tr>
              )}
              {!usersLoading && usersError && (
                <tr>
                  <td colSpan={5} style={{ padding: 16, color: T.red }}>{usersError}</td>
                </tr>
              )}
              {!usersLoading && !usersError && users.length === 0 && (
                <tr>
                  <td colSpan={5} style={{ padding: 16, color: T.t3 }}>No user accounts returned by the backend.</td>
                </tr>
              )}
              {!usersLoading && !usersError && users.slice(0, 100).map((user) => (
                <tr key={String(user.id)} onClick={() => openUser(String(user.id))}
                  style={{ borderBottom: `1px solid ${T.border}`, cursor: "pointer" }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(148,163,184,0.04)")}
                  onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}>
                  <td style={{ padding: 12, color: T.text }}>{String(user.first_name || "")} {String(user.last_name || "")}</td>
                  <td style={{ padding: 12 }}>{String(user.email || "")}</td>
                  <td style={{ padding: 12 }}>{String(user.plan || "Pro")}</td>
                  <td style={{ padding: 12 }}>{String(user.visa_status || "-")}</td>
                  <td style={{ padding: 12 }}>{String(user.created_at || "").slice(0, 10)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      {/* Activity / audit log */}
      {(eventsLoading || eventsError || events.length > 0) && (
        <Panel>
          <div style={{ padding: 18, borderBottom: `1px solid ${T.border}`, display: "flex", alignItems: "center", gap: 10 }}>
            <Activity size={17} color={T.red} />
            <div style={{ color: T.text, fontSize: 15, fontWeight: 800 }}>Recent activity</div>
          </div>
          <div style={{ padding: 18, display: "flex", flexDirection: "column", gap: 8 }}>
            {eventsLoading && <div style={{ color: T.t2, fontSize: 13 }}>Loading recent activity...</div>}
            {eventsError && <div style={{ color: T.red, fontSize: 12 }}>{eventsError}. This does not affect user-account loading.</div>}
            {!eventsLoading && !eventsError && events.slice(0, 40).map((e) => {
              const level = String(e.level || "info");
              const dot = level === "error" ? "#f87171" : level === "warning" ? "#3B82F6" : "#22c55e";
              return (
                <div key={String(e.id)} style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <span style={{ width: 8, height: 8, borderRadius: 9999, background: dot, flexShrink: 0 }} />
                  <span style={{ color: T.text, fontSize: 12, fontWeight: 600 }}>{String(e.label || e.kind || "Event")}</span>
                  <span style={{ color: T.t3, fontSize: 11, flex: 1, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{String(e.email || "")}</span>
                  <span style={{ color: T.t3, fontSize: 11, flexShrink: 0 }}>{String(e.created_at || "").slice(0, 16).replace("T", " ")}</span>
                </div>
              );
            })}
          </div>
        </Panel>
      )}

      {paymentsNote && <div style={{ color: T.t3, fontSize: 12 }}>{paymentsNote}</div>}

      {/* User drill-down modal */}
      {(detail || detailLoading) && (
        <div onClick={() => { setDetail(null); setDetailMsg(""); }}
          style={{ position: "fixed", inset: 0, zIndex: 60, background: "rgba(1,17,38,0.78)", display: "flex", alignItems: "flex-start", justifyContent: "center", padding: 24, overflowY: "auto" }}>
          <div onClick={(e) => e.stopPropagation()}
            style={{ width: "100%", maxWidth: 720, marginTop: 30, borderRadius: 18, border: `1px solid ${T.border}`, background: "#0a1626", boxShadow: "0 24px 64px rgba(0,0,0,0.5)" }}>
            <div style={{ padding: 18, borderBottom: `1px solid ${T.border}`, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <div style={{ color: T.text, fontSize: 16, fontWeight: 800 }}>User detail</div>
              <button onClick={() => { setDetail(null); setDetailMsg(""); }} style={{ background: "none", border: "none", color: T.t2, cursor: "pointer", fontSize: 18 }}>✕</button>
            </div>
            <div style={{ padding: 18 }}>
              {detailLoading && <div style={{ color: T.t2, fontSize: 13 }}>Loading…</div>}
              {detail && !detailLoading && !detail.error && (() => {
                const u = (detail.user as Record<string, unknown>) || {};
                const agreement = detail.agreement as Record<string, unknown> | null;
                const resumes = (detail.resumes as Array<Record<string, unknown>>) || [];
                const userEvents = (detail.events as Array<Record<string, unknown>>) || [];
                const reqs = (detail.role_requests as Array<Record<string, unknown>>) || [];
                const Row = ({ k, v }: { k: string; v: React.ReactNode }) => (
                  <div style={{ display: "flex", gap: 10, padding: "4px 0" }}>
                    <div style={{ width: 150, color: T.t3, fontSize: 12, flexShrink: 0 }}>{k}</div>
                    <div style={{ color: T.text, fontSize: 12, wordBreak: "break-word" }}>{v || "—"}</div>
                  </div>
                );
                return (
                  <div>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 0 }}>
                      <Row k="Name" v={`${u.first_name || ""} ${u.last_name || ""}`} />
                      <Row k="Email" v={String(u.email || "")} />
                      <Row k="Phone" v={String(u.phone || "")} />
                      <Row k="Plan" v={String(u.plan || "")} />
                      <Row k="Country" v={String(u.country || "")} />
                      <Row k="Visa" v={`${u.visa_status || ""}${u.visa_status_other ? ` (${u.visa_status_other})` : ""}`} />
                      <Row k="Experience" v={String(u.experience_years || "")} />
                      <Row k="Company" v={String(u.current_company || "")} />
                      <Row k="LinkedIn" v={String(u.linkedin_url || "")} />
                      <Row k="Access" v={`${u.payment_status || "free_access"}${u.payment_plan ? ` · ${u.payment_plan}` : ""}`} />
                      <Row k="Email verified" v={u.email_verified ? "Yes" : "No"} />
                      <Row k="Created" v={String(u.created_at || "").slice(0, 16).replace("T", " ")} />
                    </div>

                    <div style={{ marginTop: 14, paddingTop: 14, borderTop: `1px solid ${T.border}` }}>
                      <div style={{ color: T.t3, fontSize: 11, fontWeight: 700, textTransform: "uppercase", marginBottom: 6 }}>Signed agreement</div>
                      {agreement ? (
                        <div style={{ color: T.t2, fontSize: 12 }}>
                          v{String(agreement.version || "")} · {String(agreement.created_at || "").slice(0, 16).replace("T", " ")} · IP {String(agreement.ip_address || "—")} · docs: {((agreement.documents as string[]) || []).join(", ")}
                        </div>
                      ) : <div style={{ color: T.t3, fontSize: 12 }}>No agreement on record.</div>}
                    </div>

                    <div style={{ marginTop: 14, paddingTop: 14, borderTop: `1px solid ${T.border}` }}>
                      <div style={{ color: T.t3, fontSize: 11, fontWeight: 700, textTransform: "uppercase", marginBottom: 6 }}>Resumes ({resumes.length})</div>
                      {resumes.length ? resumes.map((r) => (
                        <div key={String(r.id)} style={{ color: T.t2, fontSize: 12 }}>📄 {String(r.name || r.id)} {r.active ? "· active" : ""} {r.score ? `· ATS ${r.score}` : ""}</div>
                      )) : <div style={{ color: T.t3, fontSize: 12 }}>No resumes.</div>}
                    </div>

                    {reqs.length > 0 && (
                      <div style={{ marginTop: 14, paddingTop: 14, borderTop: `1px solid ${T.border}` }}>
                        <div style={{ color: T.t3, fontSize: 11, fontWeight: 700, textTransform: "uppercase", marginBottom: 6 }}>Role requests</div>
                        {reqs.map((r) => <div key={String(r.id)} style={{ color: T.t2, fontSize: 12 }}>{String(r.role)} — {String(r.status)}</div>)}
                      </div>
                    )}

                    {userEvents.length > 0 && (
                      <div style={{ marginTop: 14, paddingTop: 14, borderTop: `1px solid ${T.border}` }}>
                        <div style={{ color: T.t3, fontSize: 11, fontWeight: 700, textTransform: "uppercase", marginBottom: 6 }}>Activity</div>
                        {userEvents.slice(0, 12).map((e) => (
                          <div key={String(e.id)} style={{ color: T.t2, fontSize: 12 }}>{String(e.label || e.kind)} · {String(e.created_at || "").slice(0, 16).replace("T", " ")}</div>
                        ))}
                      </div>
                    )}

                    <div style={{ marginTop: 16, paddingTop: 14, borderTop: `1px solid ${T.border}`, display: "flex", gap: 8, flexWrap: "wrap" }}>
                      <button onClick={triggerReset} style={{ height: 36, padding: "0 14px", borderRadius: 9, border: `1px solid ${T.border}`, background: "rgba(148,163,184,0.05)", color: T.text, cursor: "pointer", fontSize: 12, fontWeight: 700 }}>Send password reset</button>
                      <button onClick={revoke} style={{ height: 36, padding: "0 14px", borderRadius: 9, border: "none", background: "rgba(239,68,68,0.15)", color: "#f87171", cursor: "pointer", fontSize: 12, fontWeight: 700 }}>Revoke all sessions</button>
                    </div>
                    {detailMsg && <div style={{ marginTop: 10, color: "#22c55e", fontSize: 12 }}>{detailMsg}</div>}
                  </div>
                );
              })()}
              {detail && detail.error && <div style={{ color: T.red, fontSize: 13 }}>{detailMsg || "Could not load user."}</div>}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

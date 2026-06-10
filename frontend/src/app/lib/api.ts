/**
 * PlaceUp Career — Frontend API Client
 *
 * Wraps the FastAPI backend with typed helpers and a shared bearer-token
 * fetch pipeline. Access tokens stay in memory; refresh tokens are HttpOnly
 * cookies issued by the API.
 */

// Production Cloud Run backend. Used as the fallback when no VITE_API_BASE was
// baked into the build AND the app is served from a Firebase domain that has no
// /api proxy (placeupcareer.com, *.web.app, *.firebaseapp.com). On the nginx
// Cloud Run frontend (which proxies /api → backend) and on localhost dev we keep
// same-origin ("") so the proxy / dev server handles it.
// Direct backend URL — only used when served from Firebase Hosting domains
// that lack an /api proxy (*.web.app, *.firebaseapp.com). When served from
// the Cloud Run nginx frontend (placeupcareer.com, *.run.app) the browser
// uses same-origin ("") and nginx proxies /api → backend.
const PROD_API_BASE = "https://placeup-api-641222668282.us-east1.run.app";

function resolveApiBase(): string {
  const configured = (import.meta.env.VITE_API_BASE as string | undefined)?.trim();
  if (configured) return configured.replace(/\/+$/, "");
  if (typeof window !== "undefined") {
    const host = window.location.hostname;
    // Only Firebase Hosting domains need direct cross-origin calls —
    // placeupcareer.com and Cloud Run *.run.app domains use the nginx proxy.
    const isFirebaseHostingOnly =
      host.endsWith(".web.app") ||
      host.endsWith(".firebaseapp.com");
    if (isFirebaseHostingOnly) return PROD_API_BASE;
  }
  return ""; // same-origin (nginx proxy, Cloud Run, or local dev)
}

const API_BASE = resolveApiBase();
const STORAGE_TOKEN_KEY = "placeup_token";
let accessToken: string | null = null;

function getStoredToken(): string | null {
  return accessToken;
}

export function setStoredToken(token: string) {
  accessToken = token;
  if (typeof window !== "undefined") {
    localStorage.removeItem(STORAGE_TOKEN_KEY);
  }
}

export function clearStoredToken() {
  accessToken = null;
  if (typeof window !== "undefined") {
    localStorage.removeItem(STORAGE_TOKEN_KEY);
  }
}

export function getApiToken() {
  return getStoredToken();
}

function buildHeaders(headers: Record<string, string> = {}, body?: BodyInit | null) {
  const result: Record<string, string> = {
    Accept: "application/json",
    ...headers,
  };
  if (body instanceof FormData) {
    delete result["Content-Type"];
  } else if (!result["Content-Type"]) {
    result["Content-Type"] = "application/json";
  }
  const token = getStoredToken();
  if (token) result["Authorization"] = `Bearer ${token}`;
  return result;
}

async function parseResponse<T>(response: Response): Promise<T> {
  const text = await response.text();
  if (!text) {
    if (!response.ok) throw new Error(response.statusText || "Unknown error");
    return {} as T;
  }
  let data: unknown;
  try {
    data = JSON.parse(text);
  } catch {
    if (!response.ok) throw new Error(text || response.statusText || "Request failed");
    return text as unknown as T;
  }
  if (!response.ok) {
    const message =
      (data && typeof data === "object" && "detail" in (data as Record<string, unknown>)
        ? String((data as Record<string, unknown>).detail)
        : null) || response.statusText || "Request failed";
    throw new Error(message);
  }
  return data as T;
}

function shouldAttemptRefresh(path: string) {
  return ![
    "/api/auth/signin",
    "/api/auth/signup",
    "/api/auth/refresh",
    "/api/auth/logout",
    "/api/auth/demo",
  ].some((authPath) => path.startsWith(authPath));
}

// ── In-flight dedup + tiny TTL cache for GET reads ──────────────────
// Many components (Overview, JobsPage banner, Resume page) all call
// getDashboardSummary() within the same React commit. Without this,
// that's 3 separate network roundtrips. With in-flight dedup they
// share one Promise. With the 4-second TTL, page navigations also
// reuse the result instead of refetching — making the "refresh"/
// "fetching time" feel near-instant.
const _readCache = new Map<string, { at: number; data: unknown }>();
const _inflight = new Map<string, Promise<unknown>>();
const READ_TTL_MS = 4000;

function _readCacheKey(path: string, init: RequestInit) {
  return `${(init.method || "GET").toUpperCase()} ${path}`;
}

/** Invalidate the read cache — call from auth events, resume upload, etc. */
export function invalidateApiCache(prefix?: string) {
  if (!prefix) {
    _readCache.clear();
    _inflight.clear();
    return;
  }
  for (const k of _readCache.keys()) {
    if (k.includes(prefix)) _readCache.delete(k);
  }
  for (const k of _inflight.keys()) {
    if (k.includes(prefix)) _inflight.delete(k);
  }
}

async function request<T>(path: string, init: RequestInit = {}, retryOnAuth = true): Promise<T> {
  const method = (init.method || "GET").toUpperCase();
  const hasAbortSignal = Boolean(init.signal);
  const cacheable = method === "GET" && !init.body && !hasAbortSignal;
  const cacheKey = cacheable ? _readCacheKey(path, init) : "";

  if (cacheable) {
    const hit = _readCache.get(cacheKey);
    if (hit && Date.now() - hit.at < READ_TTL_MS) return hit.data as T;
    const flying = _inflight.get(cacheKey);
    if (flying) return flying as Promise<T>;
  }

  const url = `${API_BASE}${path}`;
  const body = init.body;
  const headers = buildHeaders(init.headers as Record<string, string> | undefined, body);

  const exec = (async () => {
    const response = await fetch(url, { credentials: "include", ...init, headers, body });
    if (response.status === 401 && retryOnAuth && shouldAttemptRefresh(path)) {
      try {
        await refreshAccessToken();
        return request<T>(path, init, false);
      } catch {
        clearStoredToken();
      }
    }
    const parsed = await parseResponse<T>(response);
    if (cacheable && response.ok) _readCache.set(cacheKey, { at: Date.now(), data: parsed });
    return parsed;
  })();

  if (cacheable) {
    const promise = exec.finally(() => _inflight.delete(cacheKey));
    _inflight.set(cacheKey, promise);
    return promise as Promise<T>;
  }
  return exec;
}

// Any time we know server state mutated, blow the cache so the next
// read pulls fresh data. Without this hook, the TTL cache would keep
// serving a stale dashboard for up to READ_TTL_MS after upload/delete.
if (typeof window !== "undefined") {
  window.addEventListener("placeup:resume-changed", () => invalidateApiCache());
  window.addEventListener("placeup:application-changed", () => invalidateApiCache("/api/user/"));
}

// ─── Types ───

export interface AuthResponse {
  access_token: string;
  expires_in: number;
  token_type: string;
  user_id: string;
  email: string;
  first_name: string;
  last_name: string;
  plan: string;
}

export interface TokenRefreshResponse {
  access_token: string;
  expires_in: number;
  token_type: string;
}

export interface UserProfile {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
  phone?: string;
  location?: string;
  visa_status?: string;
  experience_years?: string;
  current_role?: string;
  plan: string;
  summary?: string;
  linkedin_url?: string;
  github_url?: string;
  portfolio_url?: string;
}

export interface SessionResponse {
  authenticated: boolean;
  user?: UserProfile | null;
}

export interface AuthProvidersResponse {
  google: boolean;
}

export interface UserPreferences {
  job_preferences: string;
  notification_new_jobs: boolean;
  notification_daily_digest: boolean;
  notification_weekly_summary: boolean;
  notification_ats_updates: boolean;
  notification_marketing_emails: boolean;
  visa_status?: string;
  experience_level?: string;
  target_roles?: string[];
  target_locations?: string[];
}

export interface JobPost {
  id: string;
  title: string;
  company: string;
  location: string;
  salary?: unknown;
  match_score?: number | null;
  match?: number;
  visa?: string[] | {
    visa_opt?: boolean;
    visa_stem_opt?: boolean;
    visa_h1b?: boolean;
    h1b_verified?: boolean;
    visa_score?: number;
    visa_country?: string;
    visa_country_name?: string;
    visa_programs?: string[];
    visa_program_names?: string[];
    sponsor_verified?: boolean;
    sponsor_source?: string;
    english_friendly?: boolean;
  } | string;
  posted_at?: string;
  posted?: string;
  status?: string;
  description?: string;
  job_url?: string;
  source_url?: string;
  taxonomy_category?: string;
  role?: string;
  hiring_manager_name?: string;
  hiring_manager_email?: string;
  hiring_manager_linkedin?: string;
  responsibilities?: string[];
  requirements?: string[];
  niceToHave?: string[];
  strongKeywords?: string[];
  missingKeywords?: { kw: string; impact: string }[];
  benefits?: string[];
  approvalRate?: number;
  petitions?: number;
}

export interface JobListResponse {
  jobs: JobPost[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  filters_applied: Record<string, unknown>;
}

export interface AlertItem {
  id: string;
  title: string;
  company: string;
  location: string;
  salary: string;
  match: number;
  match_score?: number | null;
  message?: string;
  visa: string;
  time: string;
  created_at?: string;
  unread: boolean;
}

export interface AlertSettings {
  email_alerts: boolean;
  daily_digest: boolean;
  weekly_report: boolean;
}

export interface AnalyticsDashboard {
  metrics: { label: string; value: string; trend: string }[];
  applications_over_time: { month: string; apps: number; interviews: number; matches: number }[];
  ats_score_history: { version: string; score: number }[];
  total_applications?: number;
  applications_this_month?: number;
  profile_views?: number;
  profile_views_week?: number;
  resume_downloads?: number;
  resume_downloads_week?: number;
  top_match_score?: number;
  top_match_role?: string;
  time_series?: { month: string; apps: number; interviews: number; matches: number }[];
  resume_scores?: { version: string; score: number }[];
}

export interface H1BSearchResponse {
  sponsors: Array<Record<string, unknown>>;
  salary_data: Array<Record<string, unknown>>;
  total: number;
  page: number;
  page_size: number;
}

export interface VisaSponsorRow {
  employer: string;
  type: string;
  approvals: number;
  denials: number;
  rate: number;
  status: string;
}

export interface VisaDashboard {
  stats: {
    h1b_sponsors: string;
    opt_roles: string;
    avg_approval_rate: string;
    petitions_last_year: string;
  };
  sponsors: VisaSponsorRow[];
}

export interface ResumeMetadata {
  id: string;
  name: string;
  uploaded_at: string;
  score: number;
  size_bytes: number;
  active: boolean;
}

export interface NotificationItem {
  id: string;
  text: string;
  time: string;
  unread: boolean;
}

export interface DashboardSummaryAlert {
  id: string;
  title: string;
  company: string;
  match_score: number;
  message?: string;
  time: string;
  unread: boolean;
}

export interface DashboardSummary {
  resume_score: number;
  has_resume?: boolean;
  active_resume_name?: string | null;
  total_resumes: number;
  total_jobs: number;
  total_applications: number;
  recent_alerts: DashboardSummaryAlert[];
  featured_jobs?: JobPost[];
}

export interface PaymentPlan {
  id: "basic" | "pro" | "elite";
  name: string;
  price: number;
  interval: string;
  features: string[];
}

export interface AdminSummary {
  users: number;
  plans: Record<string, number>;
  payments: { configured: boolean; provider: string };
  finalscout: { multi_key_configured: boolean };
}

export interface SignupPayload {
  first_name: string;
  last_name: string;
  email: string;
  password: string;
  phone?: string;
  visa_status?: string;
  experience_level?: string;
  current_role?: string;
  current_company?: string;
  location?: string;
  linkedin_url?: string;
  target_roles?: string[];
  target_locations?: string[];
  targets?: string[];
}

export const VISA_STATUS_OPTIONS = [
  "F1",
  "F1-OPT",
  "F1-STEM OPT",
  "H-1B",
  "O-1",
  "H-4 EAD",
  "Green Card",
  "US Citizen",
  "Other",
] as const;

export const YEARS_OPTIONS = [
  "0-1 years",
  "1-3 years",
  "3-5 years",
  "5-7 years",
  "7-10 years",
  "10+ years",
] as const;

// ─── Auth ───

export interface DemoCredentials {
  email: string;
  password: string;
  note?: string;
}

export async function getDemoCredentials() {
  return request<DemoCredentials>("/api/auth/demo");
}

export async function signin(identifier: string, password: string) {
  const payload = await request<AuthResponse>("/api/auth/signin", {
    method: "POST",
    body: JSON.stringify({ email: identifier, password }),
  });
  setStoredToken(payload.access_token);
  return payload;
}

export async function signup(payload: SignupPayload) {
  const response = await request<AuthResponse>("/api/auth/signup", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  setStoredToken(response.access_token);
  return response;
}

export async function refreshAccessToken() {
  const response = await fetch(`${API_BASE}/api/auth/refresh`, {
    method: "POST",
    credentials: "include",
    headers: { Accept: "application/json" },
  });
  const payload = await parseResponse<TokenRefreshResponse>(response);
  setStoredToken(payload.access_token);
  return payload;
}

export async function getSession() {
  return request<SessionResponse>("/api/auth/session");
}

export async function getAuthProviders() {
  return request<AuthProvidersResponse>("/api/auth/oidc/providers");
}

export async function logout() {
  try {
    await request<{ ok: boolean }>("/api/auth/logout", { method: "POST" }, false);
  } finally {
    clearStoredToken();
  }
}

export function startGoogleOidc() {
  window.location.href = `${API_BASE}/api/auth/oidc/google/start`;
}

// ─── User ───

export async function getProfile() { return request<UserProfile>("/api/user/profile"); }

export async function updateProfile(payload: Partial<UserProfile>) {
  return request<UserProfile>("/api/user/profile", { method: "PUT", body: JSON.stringify(payload) });
}

export async function getPreferences() { return request<UserPreferences>("/api/user/preferences"); }

export async function updatePreferences(payload: Partial<UserPreferences>) {
  return request<UserPreferences>("/api/user/preferences", { method: "PUT", body: JSON.stringify(payload) });
}

export async function changePassword(payload: { current_password: string; new_password: string }) {
  const result = await request<{ ok: boolean }>(
    "/api/user/password",
    { method: "PUT", body: JSON.stringify(payload) },
  );
  invalidateApiCache("/api/user/");
  return result;
}

export async function deleteAccount(password: string) {
  return request<{ ok: boolean; deleted: Record<string, number> }>(
    "/api/user/account",
    { method: "DELETE", body: JSON.stringify({ password }) },
  );
}

export async function forgotPassword(email: string) {
  return request<{ ok: boolean; message: string }>(
    "/api/auth/forgot-password",
    { method: "POST", body: JSON.stringify({ email }) },
  );
}

export async function resendVerification(email: string) {
  return request<{ ok: boolean; message: string }>(
    "/api/auth/resend-verification",
    { method: "POST", body: JSON.stringify({ email }) },
  );
}

// ─── Billing ───
export interface PlanFeature { label: string; included: boolean; }
export interface PlanCard {
  slug: "basic" | "pro" | "elite";
  name: string;
  price_cents: number;
  currency: string;
  interval: string;
  description: string;
  features: PlanFeature[];
  stripe_price_id: string | null;
  recommended: boolean;
}

export async function getBillingPlans() {
  return request<PlanCard[]>("/api/billing/plans");
}

export async function getMyBilling() {
  return request<{
    plan: string;
    stripe_customer_id?: string;
    stripe_subscription_id?: string;
    subscription_status?: string;
    current_period_end?: number;
    cancel_at_period_end?: boolean;
  }>("/api/billing/me");
}

export async function startCheckout(plan: "basic" | "pro" | "elite") {
  return request<{ url: string; session_id: string }>(
    "/api/billing/checkout",
    { method: "POST", body: JSON.stringify({ plan }) },
  );
}

export async function openBillingPortal() {
  return request<{ url: string }>("/api/billing/portal");
}

export async function getNotifications() { return request<NotificationItem[]>("/api/user/notifications"); }

export async function getDashboardSummary() { return request<DashboardSummary>("/api/user/dashboard-summary"); }

export interface UserApplicationRow {
  job_id: string;
  title?: string;
  company?: string;
  location?: string;
  job_url?: string;
  description?: string;
  match_score?: number;
  status: string;
  not_applied_reason?: string;
  heard_back?: boolean;
  position_open?: boolean;
  salary_offered?: string;
  notes?: string;
  created_at?: string;
  updated_at?: string;
}

export async function saveUserApplication(payload: Omit<UserApplicationRow, "created_at" | "updated_at">) {
  const result = await request<Record<string, unknown>>(
    "/api/user/applications",
    { method: "POST", body: JSON.stringify(payload) },
  );
  // Tell the rest of the app a tracked application changed — the cache
  // layer in this file listens for this event and invalidates any
  // /api/user/* reads (applications list, dashboard summary counters).
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent("placeup:application-changed", { detail: payload }));
  }
  return result;
}

export async function getUserApplications() {
  return request<UserApplicationRow[]>("/api/user/applications");
}

export async function getResumeList() { return request<ResumeMetadata[]>("/api/user/resumes"); }

export async function uploadResume(file: File) {
  const formData = new FormData();
  formData.append("file", file);
  return request<ResumeMetadata>("/api/user/resumes/upload", { method: "POST", body: formData });
}

export async function setActiveResume(resumeId: string) {
  return request<ResumeMetadata>(`/api/user/resumes/${encodeURIComponent(resumeId)}/activate`, { method: "POST" });
}

export async function deleteResume(resumeId: string) {
  return request<{ deleted: string }>(`/api/user/resumes/${encodeURIComponent(resumeId)}`, { method: "DELETE" });
}

// ─── Jobs ───

export async function getJobs(params: Record<string, string | number | boolean | undefined> = {}, init: RequestInit = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") query.append(k, String(v));
  });
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<JobListResponse>(`/api/jobs${suffix}`, init);
}

export async function getTopMatches(params: Record<string, string | number | boolean | undefined> = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") query.append(k, String(v));
  });
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<JobListResponse>(`/api/jobs/top-matches${suffix}`);
}

export async function getJobDetail(jobId: string) { return request<JobPost>(`/api/jobs/detail/${encodeURIComponent(jobId)}`); }
export async function getJob(jobId: string) { return request<JobPost>(`/api/jobs/${encodeURIComponent(jobId)}`); }
export async function getJobStats() { return request<{ total_jobs: number; by_category: Record<string, number> }>("/api/jobs/stats"); }
export async function getJobPipelineStatus() {
  return request<{
    total_jobs: number;
    active_jobs: number;
    inactive_jobs: number;
    last_scraped_at?: string | null;
    backend?: string;
    last_run?: Record<string, unknown> | null;
  }>("/api/jobs/pipeline-status");
}
export async function getJobTaxonomy() {
  return request<{
    meta?: {
      category_count?: number;
      role_count?: number;
      backfill_term_count?: number;
      scrape_term_count?: number;
    };
    categories: Array<{ name: string; roles: Array<Record<string, unknown>> }>;
    target_countries?: Array<{ code: string; name: string }>;
    visa_programs?: Array<{ country_code: string; code: string; name: string }>;
  }>("/api/jobs/taxonomy");
}
export async function triggerScrape(payload?: Record<string, unknown>) {
  return request<Record<string, unknown>>("/api/jobs/scrape", { method: "POST", body: JSON.stringify(payload ?? {}) });
}

// ─── Alerts ───

export async function getAlerts() { return request<AlertItem[]>("/api/alerts"); }
export async function getAlertSettings() { return request<AlertSettings>("/api/alerts/settings"); }
export async function updateAlertSettings(payload: Partial<AlertSettings>) {
  return request<AlertSettings>("/api/alerts/settings", { method: "PUT", body: JSON.stringify(payload) });
}
export async function markAlertRead(alertId: string) {
  return request<AlertItem>(`/api/alerts/${encodeURIComponent(alertId)}/read`, { method: "PATCH" });
}
export async function markAllAlertsRead() {
  return request<{ updated: number }>("/api/alerts/read-all", { method: "POST" });
}
export async function deleteAlert(alertId: string) {
  return request<{ deleted: string }>(`/api/alerts/${encodeURIComponent(alertId)}`, { method: "DELETE" });
}

// ─── Analytics ───

export async function getAnalyticsDashboard() { return request<AnalyticsDashboard>("/api/analytics/dashboard"); }
export const getAnalytics = getAnalyticsDashboard;

// ─── Resume / ATS ───

export async function parseResume(file: File) {
  const formData = new FormData();
  formData.append("file", file);
  return request<Record<string, unknown>>("/api/resume/parse", { method: "POST", body: formData });
}

export async function scoreResume(file: File, jobDescription: string, jobTitle?: string, company?: string) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("job_description", jobDescription);
  if (jobTitle) formData.append("job_title", jobTitle);
  if (company) formData.append("company", company);
  return request<Record<string, unknown>>("/api/resume/score", { method: "POST", body: formData });
}

export async function extractKeywords(file: File, jobDescription: string) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("job_description", jobDescription);
  return request<Record<string, unknown>>("/api/resume/keywords", { method: "POST", body: formData });
}

// ─── Match ───

export async function matchResumeToJob(file: File, jobId: string, jobDescription?: string, jobTitle?: string) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("job_id", jobId);
  if (jobDescription) formData.append("job_description", jobDescription);
  if (jobTitle) formData.append("job_title", jobTitle);
  return request<Record<string, unknown>>("/api/match/score", { method: "POST", body: formData });
}

// ─── Visa / H-1B ───

export async function classifyJobVisa(payload: { title: string; company: string; description: string }) {
  return request<Record<string, unknown>>("/api/visa/classify", { method: "POST", body: JSON.stringify(payload) });
}

export async function getVisaDashboard() { return request<VisaDashboard>("/api/visa/dashboard"); }

export async function getVisaSponsors(params: Record<string, string | number | undefined> = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") query.append(k, String(v));
  });
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<Record<string, unknown>>(`/api/visa/sponsors${suffix}`);
}

export async function getH1BEmployer(employer: string) {
  return request<Record<string, unknown>>(`/api/visa/h1b/${encodeURIComponent(employer)}`);
}

export async function searchH1BData(employer?: string, jobTitle?: string, city?: string, year = 2024) {
  const query = new URLSearchParams();
  if (employer) query.append("employer", employer);
  if (jobTitle) query.append("job_title", jobTitle);
  if (city) query.append("city", city);
  query.append("year", String(year));
  return request<H1BSearchResponse>(`/api/visa/search?${query.toString()}`);
}

export async function getH1BSalary(jobTitle: string, location?: string, year = 2024) {
  const query = new URLSearchParams();
  query.append("job_title", jobTitle);
  if (location) query.append("location", location);
  query.append("year", String(year));
  return request<Record<string, unknown>>(`/api/visa/salary?${query.toString()}`);
}

// ─── Contacts ───

export async function listContacts(params: { company?: string; job_id?: string; source?: string; limit?: number } = {}) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") query.append(k, String(v));
  });
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request<Array<Record<string, unknown>>>(`/api/contacts${suffix}`);
}

export async function enrichContacts(payload: Record<string, unknown>) {
  return request<Record<string, unknown>>("/api/contacts/enrich", { method: "POST", body: JSON.stringify(payload) });
}

export async function draftContactEmail(payload: Record<string, unknown>) {
  return request<Record<string, unknown>>("/api/contacts/draft-email", { method: "POST", body: JSON.stringify(payload) });
}

// ─── Resume parsing (Profile Skills + Resume Quick Wins) ─────────────────

export interface ParsedResume {
  has_resume: boolean;
  name?: string;
  score?: number;
  skills?: string[];
  keywords?: string[];
  quick_wins?: { kw: string; tip: string; impact: string }[];
  target_roles?: string[];
  error?: string;
}

export async function getParsedActiveResume() {
  return request<ParsedResume>("/api/user/resume/parsed");
}

// Payments
export async function getPaymentPlans() {
  return request<{ plans: PaymentPlan[] }>("/api/payments/plans");
}

export async function createCheckout(plan_id: string) {
  return request<{ checkout_url: string; plan: PaymentPlan }>("/api/payments/checkout", {
    method: "POST",
    body: JSON.stringify({ plan_id }),
  });
}

// Admin
export async function getAdminSummary() {
  return request<AdminSummary>("/api/admin/summary");
}

export async function getAdminUsers(limit = 200) {
  return request<{ users: Array<Record<string, unknown>> }>(`/api/admin/users?limit=${limit}`);
}

export async function getAdminPayments() {
  return request<{ payments: Array<Record<string, unknown>>; note?: string }>("/api/admin/payments");
}

export async function uploadAdminFinalScoutCsv(file: File, params: { limit?: number; dry_run?: boolean; concurrency?: number } = {}) {
  const query = new URLSearchParams();
  if (params.limit) query.append("limit", String(params.limit));
  if (params.dry_run !== undefined) query.append("dry_run", String(params.dry_run));
  if (params.concurrency) query.append("concurrency", String(params.concurrency));
  const formData = new FormData();
  formData.append("file", file);
  return request<Record<string, unknown>>(`/api/admin/finalscout/upload-csv?${query.toString()}`, {
    method: "POST",
    body: formData,
  });
}

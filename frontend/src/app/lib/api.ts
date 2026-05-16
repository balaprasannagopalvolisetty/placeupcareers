/**
 * PlaceUp Career — Frontend API Client
 *
 * Wraps the FastAPI backend with typed helpers and a shared bearer-token
 * fetch pipeline. The base URL is read from `VITE_API_BASE`; when empty,
 * requests go to the deployed Google Cloud backend.
 */

const DEFAULT_API_BASE = "https://placeup-api-rui2a74muq-ue.a.run.app";
const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) || DEFAULT_API_BASE;
const STORAGE_TOKEN_KEY = "placeup_token";

function getStoredToken(): string | null {
  return typeof window !== "undefined" ? localStorage.getItem(STORAGE_TOKEN_KEY) : null;
}

export function setStoredToken(token: string) {
  if (typeof window !== "undefined") {
    localStorage.setItem(STORAGE_TOKEN_KEY, token);
  }
}

export function clearStoredToken() {
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

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const url = `${API_BASE}${path}`;
  const body = init.body;
  const headers = buildHeaders(init.headers as Record<string, string> | undefined, body);
  const response = await fetch(url, { credentials: "include", ...init, headers, body });
  return parseResponse<T>(response);
}

// ─── Types ───

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user_id: string;
  email: string;
  first_name: string;
  last_name: string;
  plan: string;
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

export interface UserPreferences {
  job_preferences: string;
  notification_new_jobs: boolean;
  notification_daily_digest: boolean;
  notification_weekly_summary: boolean;
  notification_ats_updates: boolean;
  notification_marketing_emails: boolean;
  visa_status?: string;
  experience_level?: string;
}

export interface JobPost {
  id: string;
  title: string;
  company: string;
  location: string;
  salary?: unknown;
  match_score?: number | null;
  match?: number;
  visa?: string[] | Record<string, unknown> | string;
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

export interface SignupPayload {
  first_name: string;
  last_name: string;
  email: string;
  password: string;
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

export async function signin(email: string, password: string) {
  const payload = await request<AuthResponse>("/api/auth/signin", {
    method: "POST",
    body: JSON.stringify({ email, password }),
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
  return request<{ ok: boolean }>("/api/user/password", { method: "PUT", body: JSON.stringify(payload) });
}

export async function getNotifications() { return request<NotificationItem[]>("/api/user/notifications"); }

export async function getDashboardSummary() { return request<DashboardSummary>("/api/user/dashboard-summary"); }

export async function saveUserApplication(payload: {
  job_id: string;
  title?: string;
  company?: string;
  location?: string;
  job_url?: string;
  match_score?: number;
  status: string;
  not_applied_reason?: string;
  heard_back?: boolean;
  position_open?: boolean;
  salary_offered?: string;
  notes?: string;
}) {
  return request<Record<string, unknown>>("/api/user/applications", { method: "POST", body: JSON.stringify(payload) });
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
  return request<{ categories: Array<{ name: string; roles: Array<Record<string, unknown>> }> }>("/api/jobs/taxonomy");
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

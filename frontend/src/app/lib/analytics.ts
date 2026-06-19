/**
 * PlaceUp — privacy-first analytics.
 *
 * Loads a provider (Google Analytics 4 or PostHog) ONLY after the user grants
 * cookie consent and ONLY if the relevant key is configured at build time:
 *   VITE_GA_MEASUREMENT_ID = "G-XXXXXXX"     (Google Analytics 4)
 *   VITE_POSTHOG_KEY       = "phc_..."        (PostHog)   [+ optional VITE_POSTHOG_HOST]
 *
 * No keys / no consent => every function is a safe no-op. This satisfies the
 * "cookie consent before analytics" requirement (GDPR/CCPA-friendly).
 */
const CONSENT_KEY = "placeup_cookie_consent";

const GA_ID = (import.meta.env.VITE_GA_MEASUREMENT_ID as string | undefined)?.trim() || "";
const PH_KEY = (import.meta.env.VITE_POSTHOG_KEY as string | undefined)?.trim() || "";
const PH_HOST = (import.meta.env.VITE_POSTHOG_HOST as string | undefined)?.trim() || "https://us.i.posthog.com";

let started = false;

export function consentStatus(): "granted" | "denied" | "unset" {
  try {
    const v = localStorage.getItem(CONSENT_KEY);
    return v === "granted" ? "granted" : v === "denied" ? "denied" : "unset";
  } catch {
    return "unset";
  }
}

export function setConsent(granted: boolean): void {
  try { localStorage.setItem(CONSENT_KEY, granted ? "granted" : "denied"); } catch { /* storage off */ }
  if (granted) initAnalytics();
}

declare global {
  interface Window { dataLayer?: any[]; gtag?: (...args: any[]) => void; posthog?: any }
}

export function initAnalytics(): void {
  if (started || typeof window === "undefined") return;
  if (consentStatus() !== "granted") return;
  if (GA_ID) {
    started = true;
    const s = document.createElement("script");
    s.async = true;
    s.src = `https://www.googletagmanager.com/gtag/js?id=${GA_ID}`;
    document.head.appendChild(s);
    window.dataLayer = window.dataLayer || [];
    window.gtag = function gtag() { window.dataLayer!.push(arguments); };
    window.gtag("js", new Date());
    window.gtag("config", GA_ID, { anonymize_ip: true });
  } else if (PH_KEY) {
    started = true;
    const phModule = "posthog-js";
    import(/* @vite-ignore */ phModule).then((m: any) => {
      const posthog = m.default || m;
      posthog.init(PH_KEY, { api_host: PH_HOST, capture_pageview: true, persistence: "localStorage" });
      window.posthog = posthog;
    }).catch(() => { started = false; });
  }
}

export function trackPageview(path: string): void {
  if (consentStatus() !== "granted") return;
  try {
    if (window.gtag && GA_ID) window.gtag("event", "page_view", { page_path: path });
    else if (window.posthog) window.posthog.capture("$pageview", { path });
  } catch { /* ignore */ }
}

export function trackEvent(name: string, props: Record<string, unknown> = {}): void {
  if (consentStatus() !== "granted") return;
  try {
    if (window.gtag && GA_ID) window.gtag("event", name, props);
    else if (window.posthog) window.posthog.capture(name, props);
  } catch { /* ignore */ }
}

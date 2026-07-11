import { createBrowserRouter, Navigate } from "react-router";
import { createElement, lazy, Suspense, type ComponentType } from "react";
import Layout from "./components/Layout";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { LoadingLogo } from "./components/LoadingLogo";
import Home from "./pages/Home";

// ───────────────────────────────────────────────────────────────────
// Lazy routes. Pre-split, the single bundle was 998 KB; routes that
// most users never visit (Analytics, Visa, Resumes, Settings) shouldn't
// block the first paint of the dashboard. React.lazy + a Suspense
// fallback lets the router fetch each chunk on demand.
// ───────────────────────────────────────────────────────────────────
const Dashboard = lazy(() => import("./pages/Dashboard"));
const OverviewPage = lazy(() =>
  import("./pages/Dashboard").then((m) => ({ default: m.OverviewPage }))
);
const SignIn = lazy(() => import("./pages/SignIn"));
const SignUp = lazy(() => import("./pages/SignUp"));
const NotFound = lazy(() => import("./pages/NotFound"));

const ResumePage = lazy(() =>
  import("./components/dashboard/ResumePage").then((m) => ({ default: m.ResumePage }))
);
const JobsRoute = lazy(() =>
  import("./components/dashboard/JobRoutes").then((m) => ({ default: m.JobsRoute }))
);
const JobDetailRoute = lazy(() =>
  import("./components/dashboard/JobRoutes").then((m) => ({ default: m.JobDetailRoute }))
);
const TailorResumePage = lazy(() =>
  import("./components/dashboard/TailorResumePage").then((m) => ({ default: m.TailorResumePage }))
);
const ApplicationsPage = lazy(() =>
  import("./components/dashboard/ApplicationsPage").then((m) => ({ default: m.ApplicationsPage }))
);
const AnalyticsPage = lazy(() =>
  import("./components/dashboard/AnalyticsPage").then((m) => ({ default: m.AnalyticsPage }))
);
const SettingsPage = lazy(() =>
  import("./components/dashboard/SettingsPage").then((m) => ({ default: m.SettingsPage }))
);
const AdminConsole = lazy(() => import("./pages/AdminConsole"));
const UserProfilePage = lazy(() =>
  import("./components/dashboard/UserProfilePage").then((m) => ({ default: m.UserProfilePage }))
);
const PrivacyPage = lazy(() =>
  import("./pages/Legal").then((m) => ({ default: m.PrivacyPage }))
);
const TermsPage = lazy(() =>
  import("./pages/Legal").then((m) => ({ default: m.TermsPage }))
);
const CookiesPage = lazy(() =>
  import("./pages/Legal").then((m) => ({ default: m.CookiesPage }))
);
const DisclaimerPage = lazy(() =>
  import("./pages/Legal").then((m) => ({ default: m.DisclaimerPage }))
);
const ReturnPolicyPage = lazy(() =>
  import("./pages/Legal").then((m) => ({ default: m.ReturnPolicyPage }))
);
const ForgotPasswordPage = lazy(() =>
  import("./pages/PasswordReset").then((m) => ({ default: m.ForgotPasswordPage }))
);
const ResetPasswordPage = lazy(() =>
  import("./pages/PasswordReset").then((m) => ({ default: m.ResetPasswordPage }))
);
const VerifyEmailPage = lazy(() =>
  import("./pages/PasswordReset").then((m) => ({ default: m.VerifyEmailPage }))
);

const RouteLoader = () => createElement(LoadingLogo, { label: "Loading PlaceUp" });
const DashboardJobsRedirect = () => createElement(Navigate, { to: "/dashboard/jobs", replace: true });

// Wrap each route component in our ErrorBoundary + Suspense so a
// runtime error inside e.g. JobsRoute can't blank the dashboard, and
// the lazy import can show a loader while it downloads.
const guarded = (Component: ComponentType<unknown>) => () =>
  createElement(
    ErrorBoundary,
    null,
    createElement(Suspense, { fallback: createElement(RouteLoader) }, createElement(Component))
  );

const authedGuarded = (Component: ComponentType<unknown>) => () =>
  createElement(
    ErrorBoundary,
    null,
    createElement(
      ProtectedRoute,
      null,
      createElement(Suspense, { fallback: createElement(RouteLoader) }, createElement(Component)),
    ),
  );

export const router = createBrowserRouter([
  {
    path: "/",
    Component: Layout,
    children: [
      { index: true, Component: guarded(Home) },
      {
        // ── All dashboard routes require an authenticated session.
        // authedGuarded() wraps each child in ProtectedRoute so the
        // unauthenticated visitor bounces to /signin BEFORE any child
        // attempts an API call. ProtectedRoute also remembers the
        // intended URL so signin can return the user there.
        path: "dashboard",
        Component: authedGuarded(Dashboard),
        children: [
          { index: true, Component: authedGuarded(OverviewPage) },
          { path: "resumes", Component: authedGuarded(ResumePage) },
          { path: "jobs", Component: authedGuarded(JobsRoute) },
          { path: "jobs/:jobId", Component: authedGuarded(JobDetailRoute) },
          { path: "tailor", Component: authedGuarded(TailorResumePage) },
          { path: "alerts", Component: authedGuarded(DashboardJobsRedirect) },
          { path: "applications", Component: authedGuarded(ApplicationsPage) },
          { path: "analytics", Component: authedGuarded(AnalyticsPage) },
          { path: "settings", Component: authedGuarded(SettingsPage) },
          { path: "profile", Component: authedGuarded(UserProfilePage) },
        ],
      },
      // Private admin console — unguessable path, not linked anywhere in the
      // UI. Real protection is the backend ADMIN_EMAILS allowlist.
      { path: "ops-console-9c2f1a8b7e", Component: authedGuarded(AdminConsole) },
      { path: "signin", Component: guarded(SignIn) },
      { path: "signup", Component: guarded(SignUp) },
      { path: "forgot-password", Component: guarded(ForgotPasswordPage) },
      { path: "reset-password", Component: guarded(ResetPasswordPage) },
      { path: "verify-email", Component: guarded(VerifyEmailPage) },
      { path: "privacy", Component: guarded(PrivacyPage) },
      { path: "terms", Component: guarded(TermsPage) },
      { path: "cookies", Component: guarded(CookiesPage) },
      { path: "disclaimer", Component: guarded(DisclaimerPage) },
      { path: "return-policy", Component: guarded(ReturnPolicyPage) },
      // Catch-all 404 — anything that doesn't match a real route lands
      // here instead of rendering an empty Layout shell.
      { path: "*", Component: guarded(NotFound) },
    ],
  },
]);

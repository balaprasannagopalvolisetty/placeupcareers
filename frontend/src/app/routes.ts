import { createBrowserRouter } from "react-router";
import { createElement, lazy, Suspense, type ComponentType } from "react";
import Layout from "./components/Layout";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { ProtectedRoute } from "./components/ProtectedRoute";

// ───────────────────────────────────────────────────────────────────
// Lazy routes. Pre-split, the single bundle was 998 KB; routes that
// most users never visit (Analytics, Visa, Resumes, Settings) shouldn't
// block the first paint of the dashboard. React.lazy + a Suspense
// fallback lets the router fetch each chunk on demand.
// ───────────────────────────────────────────────────────────────────
const Home = lazy(() => import("./pages/Home"));
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
const VisaTrackerPage = lazy(() =>
  import("./components/dashboard/VisaTrackerPage").then((m) => ({ default: m.VisaTrackerPage }))
);
const AlertsPage = lazy(() =>
  import("./components/dashboard/AlertsPage").then((m) => ({ default: m.AlertsPage }))
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
const BillingPage = lazy(() =>
  import("./components/dashboard/BillingPage").then((m) => ({ default: m.BillingPage }))
);
const AdminPage = lazy(() =>
  import("./components/dashboard/AdminPage").then((m) => ({ default: m.AdminPage }))
);
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
const ForgotPasswordPage = lazy(() =>
  import("./pages/PasswordReset").then((m) => ({ default: m.ForgotPasswordPage }))
);
const ResetPasswordPage = lazy(() =>
  import("./pages/PasswordReset").then((m) => ({ default: m.ResetPasswordPage }))
);
const VerifyEmailPage = lazy(() =>
  import("./pages/PasswordReset").then((m) => ({ default: m.VerifyEmailPage }))
);

// Tiny inline loader so dashboard switches don't flash blank while
// the chunk downloads. Matches the index.html bootstrap colors so the
// transition feels intentional.
const RouteLoader = () =>
  createElement(
    "div",
    {
      style: {
        padding: "60px 20px",
        textAlign: "center",
        color: "rgba(242,238,179,0.55)",
        fontFamily: "'Plus Jakarta Sans', sans-serif",
        fontSize: 13,
      },
    },
    "Loading…"
  );

// Wrap each route component in our ErrorBoundary + Suspense so a
// runtime error inside e.g. JobsRoute can't blank the dashboard, and
// the lazy import can show a loader while it downloads.
const guarded = (Component: ComponentType<unknown>) => () =>
  createElement(
    ErrorBoundary,
    null,
    createElement(Suspense, { fallback: createElement(RouteLoader) }, createElement(Component))
  );

// Same as guarded() but also requires an authenticated session. Use
// this for every route under /dashboard/* so a direct URL hit by an
// unauthenticated visitor redirects to /signin instead of rendering
// the dashboard shell and 401-ing API calls inside it.
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
          { path: "visa", Component: authedGuarded(VisaTrackerPage) },
          { path: "alerts", Component: authedGuarded(AlertsPage) },
          { path: "applications", Component: authedGuarded(ApplicationsPage) },
          { path: "analytics", Component: authedGuarded(AnalyticsPage) },
          { path: "billing", Component: authedGuarded(BillingPage) },
          { path: "settings", Component: authedGuarded(SettingsPage) },
          { path: "admin", Component: authedGuarded(AdminPage) },
          { path: "profile", Component: authedGuarded(UserProfilePage) },
        ],
      },
      { path: "signin", Component: guarded(SignIn) },
      { path: "signup", Component: guarded(SignUp) },
      { path: "forgot-password", Component: guarded(ForgotPasswordPage) },
      { path: "reset-password", Component: guarded(ResetPasswordPage) },
      { path: "verify-email", Component: guarded(VerifyEmailPage) },
      { path: "privacy", Component: guarded(PrivacyPage) },
      { path: "terms", Component: guarded(TermsPage) },
      { path: "cookies", Component: guarded(CookiesPage) },
      // Catch-all 404 — anything that doesn't match a real route lands
      // here instead of rendering an empty Layout shell.
      { path: "*", Component: guarded(NotFound) },
    ],
  },
]);

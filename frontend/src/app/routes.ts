import { createBrowserRouter } from "react-router";
import { createElement, lazy, Suspense, type ComponentType } from "react";
import Layout from "./components/Layout";
import { ErrorBoundary } from "./components/ErrorBoundary";

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
const AnalyticsPage = lazy(() =>
  import("./components/dashboard/AnalyticsPage").then((m) => ({ default: m.AnalyticsPage }))
);
const SettingsPage = lazy(() =>
  import("./components/dashboard/SettingsPage").then((m) => ({ default: m.SettingsPage }))
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

export const router = createBrowserRouter([
  {
    path: "/",
    Component: Layout,
    children: [
      { index: true, Component: guarded(Home) },
      {
        path: "dashboard",
        Component: guarded(Dashboard),
        children: [
          { index: true, Component: guarded(OverviewPage) },
          { path: "resumes", Component: guarded(ResumePage) },
          { path: "jobs", Component: guarded(JobsRoute) },
          { path: "jobs/:jobId", Component: guarded(JobDetailRoute) },
          { path: "visa", Component: guarded(VisaTrackerPage) },
          { path: "alerts", Component: guarded(AlertsPage) },
          { path: "analytics", Component: guarded(AnalyticsPage) },
          { path: "settings", Component: guarded(SettingsPage) },
          { path: "profile", Component: guarded(UserProfilePage) },
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

import { createBrowserRouter } from "react-router";
import { createElement } from "react";
import Home from "./pages/Home";
import Dashboard, { OverviewPage } from "./pages/Dashboard";
import SignIn from "./pages/SignIn";
import SignUp from "./pages/SignUp";
import Layout from "./components/Layout";
import { ResumePage } from "./components/dashboard/ResumePage";
import { JobsRoute, JobDetailRoute } from "./components/dashboard/JobRoutes";
import { VisaTrackerPage } from "./components/dashboard/VisaTrackerPage";
import { AlertsPage } from "./components/dashboard/AlertsPage";
import { AnalyticsPage } from "./components/dashboard/AnalyticsPage";
import { SettingsPage } from "./components/dashboard/SettingsPage";
import { UserProfilePage } from "./components/dashboard/UserProfilePage";
import { ErrorBoundary } from "./components/ErrorBoundary";

// Wrap a route component in our ErrorBoundary so a runtime render error
// inside e.g. JobsRoute can't blank the entire dashboard.
const guarded = (Component: React.ComponentType<unknown>) => () =>
  createElement(ErrorBoundary, null, createElement(Component));

export const router = createBrowserRouter([
  {
    path: "/",
    Component: Layout,
    children: [
      { index: true, Component: Home },
      {
        path: "dashboard",
        Component: Dashboard,
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
      { path: "signin", Component: SignIn },
      { path: "signup", Component: SignUp },
    ],
  },
]);

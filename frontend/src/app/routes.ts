import { createBrowserRouter } from "react-router";
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
          { index: true, Component: OverviewPage },
          { path: "resumes", Component: ResumePage },
          { path: "jobs", Component: JobsRoute },
          { path: "jobs/:jobId", Component: JobDetailRoute },
          { path: "visa", Component: VisaTrackerPage },
          { path: "alerts", Component: AlertsPage },
          { path: "analytics", Component: AnalyticsPage },
          { path: "settings", Component: SettingsPage },
          { path: "profile", Component: UserProfilePage },
        ],
      },
      { path: "signin", Component: SignIn },
      { path: "signup", Component: SignUp },
    ],
  },
]);

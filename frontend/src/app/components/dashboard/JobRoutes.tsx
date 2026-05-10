/**
 * Route adapters that bridge react-router URL params to the dashboard
 * page components, which were originally designed to take props from
 * a parent. Keeps the page components untouched.
 */

import { useNavigate, useParams } from "react-router";
import { JobsPage } from "./JobsPage";
import { JobDetailPage } from "./JobDetailPage";

export function JobsRoute() {
  const navigate = useNavigate();
  return <JobsPage onJobClick={(id) => navigate(`/dashboard/jobs/${id}`)} />;
}

export function JobDetailRoute() {
  const navigate = useNavigate();
  const params = useParams<{ jobId: string }>();
  return (
    <JobDetailPage
      jobId={params.jobId ?? ""}
      onBack={() => navigate("/dashboard/jobs")}
    />
  );
}

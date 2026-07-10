import { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";
import { useAuth } from "../context/AuthContext";

/**
 * Gate every /dashboard/* route behind an active session.
 *
 * Without this, anyone could type `/dashboard/settings` (or any deep
 * dashboard URL) directly into the address bar and the page would render
 * client-side — the backend API calls would 401, but the LAYOUT shell
 * was already visible. That's both a leak of UI structure and a bad
 * user experience.
 *
 * Behaviour:
 *   - While the AuthContext is still resolving the session (cookie
 *     refresh on first paint), render a small skeleton. This avoids
 *     a flash of "Sign in" while a logged-in user's session is being
 *     re-hydrated from the refresh cookie.
 *   - Once resolved: if no user, redirect to /signin and remember the
 *     intended URL so the user can be sent back after login.
 *   - If authed, render children unchanged.
 */
export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user, loading, isAuthenticated } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div
        role="status"
        aria-live="polite"
        style={{
          padding: "60px 20px",
          textAlign: "center",
          color: "var(--pu-242-238-179-055)",
          fontFamily: "'Plus Jakarta Sans', sans-serif",
          fontSize: 13,
        }}
      >
        Verifying your session…
      </div>
    );
  }

  if (!isAuthenticated || !user) {
    // Round-trip the deep-link the user tried to visit so /signin can
    // navigate(state.from || "/dashboard") after a successful sign-in.
    return (
      <Navigate
        to="/signin"
        replace
        state={{ from: `${location.pathname}${location.search}` }}
      />
    );
  }

  return <>{children}</>;
}

export default ProtectedRoute;

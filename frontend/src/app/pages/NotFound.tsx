import { Link } from "react-router";

/**
 * 404 fallback. Previously, hitting an unknown URL (typo, stale link,
 * old marketing redirect) just rendered the Layout shell with an empty
 * body — looked broken. This page gives the user an explicit "you took
 * a wrong turn, here's how to get back" message.
 */
export default function NotFound() {
  return (
    <main
      role="main"
      style={{
        minHeight: "calc(100vh - 80px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 24,
      }}
    >
      <div
        style={{
          maxWidth: 460,
          width: "100%",
          padding: 32,
          borderRadius: 20,
          background: "var(--pu-15-30-55-055)",
          border: "1px solid var(--pu-148-163-184-01)",
          color: "var(--pu-f1f5f9-t)",
          fontFamily: "'Plus Jakarta Sans', sans-serif",
          textAlign: "center",
        }}
      >
        <div
          style={{
            fontSize: 56,
            fontWeight: 800,
            background: "linear-gradient(135deg, var(--pu-2563eb), var(--pu-0ea5e9))",
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
            backgroundClip: "text",
            marginBottom: 4,
            lineHeight: 1,
          }}
        >
          404
        </div>
        <h1 style={{ fontSize: 18, fontWeight: 700, margin: "8px 0 8px" }}>
          Page not found
        </h1>
        <p
          style={{
            fontSize: 14,
            lineHeight: 1.5,
            color: "var(--pu-226-232-240-072)",
            marginBottom: 22,
          }}
        >
          The page you're looking for might have moved, or never existed. Head
          back to your dashboard and pick up where you left off.
        </p>
        <div style={{ display: "flex", gap: 10, justifyContent: "center", flexWrap: "wrap" }}>
          <Link
            to="/dashboard"
            style={{
              padding: "10px 18px",
              borderRadius: 10,
              background: "linear-gradient(135deg, var(--pu-2563eb), var(--pu-0ea5e9))",
              color: "var(--pu-ffffff-t)",
              fontWeight: 600,
              fontSize: 13,
              textDecoration: "none",
            }}
          >
            Go to dashboard
          </Link>
          <Link
            to="/"
            style={{
              padding: "10px 18px",
              borderRadius: 10,
              border: "1px solid var(--pu-148-163-184-018)",
              color: "var(--pu-f1f5f9-t)",
              fontWeight: 500,
              fontSize: 13,
              textDecoration: "none",
            }}
          >
            Home
          </Link>
        </div>
      </div>
    </main>
  );
}

import { createRoot } from "react-dom/client";
import App from "./app/App.tsx";
import { AuthProvider } from "./app/context/AuthContext";
import { CookieConsent } from "./app/components/CookieConsent";
import { initObservability } from "./app/lib/observability";
import "./styles/index.css";

const PRELOAD_RELOAD_KEY = "placeup_preload_reload";

if (typeof window !== "undefined") {
  window.addEventListener("vite:preloadError", (event) => {
    event.preventDefault();
    if (sessionStorage.getItem(PRELOAD_RELOAD_KEY) === "1") return;
    sessionStorage.setItem(PRELOAD_RELOAD_KEY, "1");
    window.location.reload();
  });
  window.addEventListener("load", () => {
    sessionStorage.removeItem(PRELOAD_RELOAD_KEY);
  });
}

// Install global error handlers BEFORE React renders. If a component
// throws during initial render we want to capture it instead of seeing
// "Uncaught Error" silently in the user's console.
initObservability().catch(() => {
  // Telemetry init must never block app boot.
});

createRoot(document.getElementById("root")!).render(
  <AuthProvider>
    <App />
    <CookieConsent />
  </AuthProvider>,
);

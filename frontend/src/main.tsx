import { createRoot } from "react-dom/client";
import App from "./app/App.tsx";
import { AuthProvider } from "./app/context/AuthContext";
import { initObservability } from "./app/lib/observability";
import "./styles/index.css";

// Install global error handlers BEFORE React renders. If a component
// throws during initial render we want to capture it instead of seeing
// "Uncaught Error" silently in the user's console.
initObservability().catch(() => {
  // Telemetry init must never block app boot.
});

createRoot(document.getElementById("root")!).render(
  <AuthProvider>
    <App />
  </AuthProvider>,
);

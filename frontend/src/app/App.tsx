import { RouterProvider } from "react-router";
import { router } from "./routes";
import { ErrorBoundary } from "./components/ErrorBoundary";

export default function App() {
  // Top-level error boundary: a render crash in any route shows a recoverable
  // error card instead of a blank white screen for the user.
  return (
    <ErrorBoundary>
      <RouterProvider router={router} />
    </ErrorBoundary>
  );
}

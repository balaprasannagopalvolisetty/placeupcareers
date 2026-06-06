import { useEffect, useState } from "react";
import { useLocation } from "react-router";

const blockedShortcutMessage = "Protected content";

export function PrivacyGuard() {
  const location = useLocation();
  const protectedRoute = location.pathname.startsWith("/dashboard");
  const [shielded, setShielded] = useState(false);
  const [notice, setNotice] = useState("");

  useEffect(() => {
    if (!notice) return;
    const timeout = window.setTimeout(() => setNotice(""), 1600);
    return () => window.clearTimeout(timeout);
  }, [notice]);

  useEffect(() => {
    document.body.classList.toggle("placeup-privacy-protected", protectedRoute);
    if (!protectedRoute) {
      setShielded(false);
      return () => document.body.classList.remove("placeup-privacy-protected");
    }

    const block = (event: Event) => {
      event.preventDefault();
      event.stopPropagation();
      setNotice(blockedShortcutMessage);
    };

    const onKeyDown = (event: KeyboardEvent) => {
      const key = event.key.toLowerCase();
      const hasModifier = event.ctrlKey || event.metaKey;
      const blocked =
        event.key === "PrintScreen" ||
        event.key === "F12" ||
        (hasModifier && ["p", "s", "u"].includes(key)) ||
        (hasModifier && event.shiftKey && ["c", "i", "j", "s"].includes(key));

      if (!blocked) return;
      block(event);
      setShielded(true);
      if (event.key === "PrintScreen") {
        navigator.clipboard?.writeText("Protected by PlaceUp Career").catch(() => {});
      }
      window.setTimeout(() => setShielded(false), 1200);
    };

    const onVisibilityChange = () => setShielded(document.hidden);
    const onBlur = () => setShielded(true);
    const onFocus = () => setShielded(false);
    const onBeforePrint = (event: Event) => {
      block(event);
      setShielded(true);
    };
    const onAfterPrint = () => setShielded(false);

    document.addEventListener("contextmenu", block, true);
    document.addEventListener("copy", block, true);
    document.addEventListener("cut", block, true);
    document.addEventListener("dragstart", block, true);
    document.addEventListener("selectstart", block, true);
    document.addEventListener("keydown", onKeyDown, true);
    document.addEventListener("visibilitychange", onVisibilityChange);
    window.addEventListener("blur", onBlur);
    window.addEventListener("focus", onFocus);
    window.addEventListener("beforeprint", onBeforePrint);
    window.addEventListener("afterprint", onAfterPrint);

    return () => {
      document.body.classList.remove("placeup-privacy-protected");
      document.removeEventListener("contextmenu", block, true);
      document.removeEventListener("copy", block, true);
      document.removeEventListener("cut", block, true);
      document.removeEventListener("dragstart", block, true);
      document.removeEventListener("selectstart", block, true);
      document.removeEventListener("keydown", onKeyDown, true);
      document.removeEventListener("visibilitychange", onVisibilityChange);
      window.removeEventListener("blur", onBlur);
      window.removeEventListener("focus", onFocus);
      window.removeEventListener("beforeprint", onBeforePrint);
      window.removeEventListener("afterprint", onAfterPrint);
    };
  }, [protectedRoute]);

  return (
    <>
      <style>{`
        body.placeup-privacy-protected,
        body.placeup-privacy-protected * {
          -webkit-user-select: none !important;
          user-select: none !important;
        }
        body.placeup-privacy-protected img,
        body.placeup-privacy-protected video {
          -webkit-user-drag: none !important;
        }
        @media print {
          body.placeup-privacy-protected * {
            visibility: hidden !important;
          }
          body.placeup-privacy-protected::before {
            content: "Protected by PlaceUp Career";
            visibility: visible !important;
            position: fixed;
            inset: 0;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #111827;
            font-family: Inter, sans-serif;
            font-size: 24px;
            font-weight: 700;
          }
        }
      `}</style>

      {protectedRoute && shielded && (
        <div
          aria-live="polite"
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 2147483647,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "rgba(1, 17, 38, 0.94)",
            backdropFilter: "blur(18px)",
            color: "#ffffff",
            fontFamily: "'Plus Jakarta Sans', sans-serif",
          }}
        >
          <div style={{ textAlign: "center", padding: 24 }}>
            <div style={{ fontSize: 22, fontWeight: 800, lineHeight: 1.2 }}>PlaceUp Career</div>
            <div style={{ marginTop: 10, fontSize: 14, fontWeight: 600, lineHeight: 1.5, color: "#c7d2fe" }}>
              Protected view
            </div>
          </div>
        </div>
      )}

      {protectedRoute && notice && !shielded && (
        <div
          role="status"
          style={{
            position: "fixed",
            right: 20,
            bottom: 20,
            zIndex: 2147483646,
            border: "1px solid rgba(167, 139, 250, 0.45)",
            borderRadius: 14,
            background: "rgba(15, 23, 42, 0.92)",
            boxShadow: "0 18px 55px rgba(0, 0, 0, 0.28)",
            color: "#ffffff",
            padding: "12px 16px",
            fontSize: 13,
            fontWeight: 700,
            lineHeight: 1.2,
          }}
        >
          {notice}
        </div>
      )}
    </>
  );
}

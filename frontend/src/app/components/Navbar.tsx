import { Link, useLocation } from "react-router";
import { motion, AnimatePresence } from "motion/react";
import { Menu, X } from "lucide-react";
import { useState, useCallback } from "react";
import { useAuth } from "../context/AuthContext";
import { BrandLogo } from "./BrandLogo";

// Clean, light SaaS navbar. Self-contained tokens (matches Home page).
const N = {
  border: "#E2E8F0",
  text: "#0F172A",
  t2: "#475569",
  accent: "#2563EB",
  grad: "linear-gradient(135deg, #2563EB, #0EA5E9)",
};
const FONT = "'Plus Jakarta Sans', sans-serif";

const navItems = [
  { label: "How It Works", id: "how-it-works" },
  { label: "Features",     id: "features" },
  { label: "Contact Us",   id: "contact" },
];

function Wordmark() {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", padding: "4px 9px", borderRadius: 12, background: "linear-gradient(135deg, #011126, #1E3A8A)", boxShadow: "0 8px 18px rgba(15,23,42,0.16)" }}>
      <BrandLogo height={36} />
    </span>
  );
}

export function Navbar() {
  const { isAuthenticated } = useAuth();
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const isHome = location.pathname === "/";

  const scrollTo = useCallback((id: string) => {
    if (!isHome) { window.location.href = `/#${id}`; return; }
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
    setOpen(false);
  }, [isHome]);

  return (
    <motion.nav
      initial={{ y: -70 }}
      animate={{ y: 0 }}
      transition={{ duration: 0.5, ease: [0.76, 0, 0.24, 1] }}
      style={{
        position: "fixed", top: 0, left: 0, right: 0, zIndex: 100,
        backdropFilter: "blur(14px)", WebkitBackdropFilter: "blur(14px)",
        background: "rgba(255,255,255,0.88)",
        borderBottom: `1px solid ${N.border}`,
        height: 64,
      }}
    >
      <div style={{ maxWidth: 1280, margin: "0 auto", padding: "0 24px", height: "100%", display: "flex", alignItems: "center", justifyContent: "space-between" }}>

        {/* Logo */}
        <Link to={isAuthenticated ? "/dashboard" : "/"} style={{ display: "flex", alignItems: "center", textDecoration: "none" }}>
          <Wordmark />
        </Link>

        {/* Desktop nav */}
        <div className="hidden md:flex items-center" style={{ gap: 4 }}>
          {navItems.map((item) => (
            <button
              key={item.label}
              onClick={() => scrollTo(item.id)}
              style={{
                padding: "8px 14px", borderRadius: 8, border: "none",
                background: "transparent", cursor: "pointer",
                color: N.t2, fontSize: 14, fontFamily: FONT, fontWeight: 600,
                transition: "color 0.2s",
              }}
              onMouseEnter={(e) => (e.currentTarget.style.color = N.text)}
              onMouseLeave={(e) => (e.currentTarget.style.color = N.t2)}
            >
              {item.label}
            </button>
          ))}
        </div>

        {/* Right controls */}
        <div className="hidden md:flex items-center" style={{ gap: 10 }}>
          <Link to="/signin" style={{ padding: "8px 14px", borderRadius: 8, color: N.t2, fontSize: 14, fontFamily: FONT, fontWeight: 600, textDecoration: "none" }}
            onMouseEnter={(e) => (e.currentTarget.style.color = N.text)}
            onMouseLeave={(e) => (e.currentTarget.style.color = N.t2)}
          >
            Sign In
          </Link>
          <Link to="/signup" style={{
            padding: "10px 20px", borderRadius: 10,
            background: N.grad,
            color: "#fff", fontSize: 14, fontFamily: FONT, fontWeight: 700,
            textDecoration: "none",
            boxShadow: "0 6px 16px rgba(37,99,235,0.25)",
          }}>
            Get Started
          </Link>
        </div>

        {/* Mobile hamburger */}
        <button className="md:hidden" onClick={() => setOpen(!open)} style={{ background: "none", border: "none", cursor: "pointer", color: N.text }}>
          {open ? <X size={22} /> : <Menu size={22} />}
        </button>
      </div>

      {/* Mobile drawer */}
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, x: "100%" }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: "100%" }}
            transition={{ duration: 0.25, ease: "easeInOut" }}
            style={{
              position: "fixed", top: 64, right: 0, bottom: 0, width: "100%",
              background: "rgba(255,255,255,0.98)", backdropFilter: "blur(14px)",
              padding: "24px", display: "flex", flexDirection: "column", gap: 4,
              zIndex: 99,
            }}
          >
            {navItems.map((item) => (
              <button
                key={item.label}
                onClick={() => scrollTo(item.id)}
                style={{
                  display: "block", width: "100%", padding: "16px",
                  background: "transparent", border: "none", cursor: "pointer", textAlign: "left",
                  color: N.text, fontSize: 16, fontFamily: FONT, fontWeight: 600,
                  borderBottom: `1px solid ${N.border}`,
                }}
              >
                {item.label}
              </button>
            ))}
            <div style={{ marginTop: 24, display: "flex", flexDirection: "column", gap: 12 }}>
              <Link to="/signin" onClick={() => setOpen(false)} style={{ padding: "14px", borderRadius: 12, textAlign: "center", border: `1px solid ${N.border}`, color: N.text, fontFamily: FONT, fontWeight: 600, textDecoration: "none" }}>Sign In</Link>
              <Link to="/signup" onClick={() => setOpen(false)} style={{ padding: "14px", borderRadius: 12, textAlign: "center", background: N.grad, color: "#fff", fontFamily: FONT, fontWeight: 700, textDecoration: "none" }}>Get Started Free</Link>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.nav>
  );
}

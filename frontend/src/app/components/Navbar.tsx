import { Link, useLocation } from "react-router";
import { motion, AnimatePresence } from "motion/react";
import { Menu, X } from "lucide-react";
import { useState, useCallback } from "react";
import { C, F } from "../theme";
import { useAuth } from "../context/AuthContext";

const navItems = [
  { label: "How It Works", id: "how-it-works" },
  { label: "Features",     id: "features" },
  { label: "Pricing",      id: "pricing" },
  { label: "Contact Us",   id: "contact" },
];

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
      transition={{ duration: 0.6, ease: [0.76, 0, 0.24, 1] }}
      style={{
        position: "fixed", top: 0, left: 0, right: 0, zIndex: 100,
        backdropFilter: "blur(20px)", WebkitBackdropFilter: "blur(20px)",
        background: C.bg,
        borderBottom: `1px solid ${C.border}`,
        height: 64,
      }}
    >
      <div style={{ maxWidth: 1280, margin: "0 auto", padding: "0 32px", height: "100%", display: "flex", alignItems: "center", justifyContent: "space-between" }}>

        {/* Logo */}
        <Link to={isAuthenticated ? "/dashboard" : "/"} style={{ display: "flex", alignItems: "center", textDecoration: "none" }}>
          <img src="/logo_light.png" alt="PlaceUp Career" style={{ height: 42, width: "auto", objectFit: "contain", display: "block" }} />
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
                color: C.t2, fontSize: 14, fontFamily: F.sans, fontWeight: 500,
                transition: "color 0.2s",
              }}
              onMouseEnter={(e) => (e.currentTarget.style.color = C.text)}
              onMouseLeave={(e) => (e.currentTarget.style.color = C.t2)}
            >
              {item.label}
            </button>
          ))}
        </div>

        {/* Right controls */}
        <div className="hidden md:flex items-center" style={{ gap: 10 }}>
          <Link to="/signin" style={{ padding: "8px 14px", borderRadius: 8, color: C.t2, fontSize: 14, fontFamily: F.sans, fontWeight: 500, textDecoration: "none" }}
            onMouseEnter={(e) => (e.currentTarget.style.color = C.text)}
            onMouseLeave={(e) => (e.currentTarget.style.color = C.t2)}
          >
            Sign In
          </Link>
          <Link to="/signup" style={{
            padding: "9px 20px", borderRadius: 12,
            background: C.grad,
            color: "#fff", fontSize: 14, fontFamily: F.sans, fontWeight: 600,
            textDecoration: "none",
            boxShadow: "0 0 20px rgba(237,125,43,0.35)",
          }}>
            Get Started →
          </Link>
        </div>

        {/* Mobile hamburger */}
        <button className="md:hidden" onClick={() => setOpen(!open)} style={{ background: "none", border: "none", cursor: "pointer", color: C.text }}>
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
            transition={{ duration: 0.3, ease: "easeInOut" }}
            style={{
              position: "fixed", top: 64, right: 0, bottom: 0, width: "100%",
              background: "rgba(1,17,38,0.97)", backdropFilter: "blur(20px)",
              padding: "32px 24px", display: "flex", flexDirection: "column", gap: 4,
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
                  color: C.t2, fontSize: 16, fontFamily: F.sans, fontWeight: 500,
                  borderBottom: "1px solid rgba(242,238,179,0.06)",
                }}
              >
                {item.label}
              </button>
            ))}
            <div style={{ marginTop: 24, display: "flex", flexDirection: "column", gap: 12 }}>
              <Link to="/signin" style={{ padding: "14px", borderRadius: 12, textAlign: "center", border: "1px solid rgba(242,238,179,0.1)", color: C.text, fontFamily: F.sans, textDecoration: "none" }}>Sign In</Link>
              <Link to="/signup" style={{ padding: "14px", borderRadius: 12, textAlign: "center", background: C.grad, color: "#fff", fontFamily: F.sans, fontWeight: 600, textDecoration: "none" }}>Get Started Free</Link>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.nav>
  );
}

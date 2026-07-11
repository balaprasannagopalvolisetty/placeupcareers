import { Link, useLocation } from "react-router";
import { motion, AnimatePresence } from "motion/react";
import { Menu, X } from "lucide-react";
import { useState, useCallback } from "react";
import { useAuth } from "../context/AuthContext";
import { BrandLogo } from "./BrandLogo";
import { ThemeToggle } from "./Layout";

// Clean, light SaaS navbar. Self-contained tokens (matches Home page).
const N = {
  border: "var(--pu-e2e8f0-b)",
  text: "var(--pu-0f172a-t)",
  t2: "var(--pu-475569-t)",
  accent: "var(--pu-2563eb)",
  grad: "linear-gradient(135deg, var(--pu-2563eb), var(--pu-0ea5e9))",
};
const FONT = "'Plus Jakarta Sans', sans-serif";

const navItems = [
  { label: "How It Works", id: "how-it-works" },
  { label: "Features",     id: "features" },
  { label: "Pricing",      id: "pricing" },
  { label: "Contact Us",   id: "contact" },
];

function Wordmark() {
  return <BrandLogo variant="dark" height={42} />;
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
    <nav
      style={{
        position: "fixed", top: 0, left: 0, right: 0, zIndex: 100,
        backdropFilter: "blur(14px)", WebkitBackdropFilter: "blur(14px)",
        background: "var(--pu-255-255-255-088)",
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
          <ThemeToggle />
          <Link to="/signin" style={{ padding: "8px 14px", borderRadius: 8, color: N.t2, fontSize: 14, fontFamily: FONT, fontWeight: 600, textDecoration: "none" }}
            onMouseEnter={(e) => (e.currentTarget.style.color = N.text)}
            onMouseLeave={(e) => (e.currentTarget.style.color = N.t2)}
          >
            Sign In
          </Link>
          <Link to="/signup" style={{
            padding: "10px 20px", borderRadius: 10,
            background: N.grad,
            color: "var(--pu-ffffff-t)", fontSize: 14, fontFamily: FONT, fontWeight: 700,
            textDecoration: "none",
            boxShadow: "0 6px 16px var(--pu-37-99-235-025)",
          }}>
            Get Started
          </Link>
        </div>

        {/* Mobile: theme toggle + hamburger. Layout via Tailwind classes only —
            an inline display would override the responsive `md:hidden`. */}
        <div className="flex md:hidden items-center gap-2.5">
          <ThemeToggle size={30} />
          <button onClick={() => setOpen(!open)} style={{ background: "none", border: "none", cursor: "pointer", color: N.text }}>
            {open ? <X size={22} /> : <Menu size={22} />}
          </button>
        </div>
      </div>

      {/* Mobile drawer */}
      <AnimatePresence>
        {open && (
          <motion.div
            className="flex md:hidden"
            initial={{ opacity: 0, x: "100%" }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: "100%" }}
            transition={{ duration: 0.25, ease: "easeInOut" }}
            style={{
              position: "fixed", top: 64, right: 0, bottom: 0, width: "100%",
              background: "var(--pu-255-255-255-098)", backdropFilter: "blur(14px)",
              padding: "24px", flexDirection: "column", gap: 4,
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
              <Link to="/signup" onClick={() => setOpen(false)} style={{ padding: "14px", borderRadius: 12, textAlign: "center", background: N.grad, color: "var(--pu-ffffff-t)", fontFamily: FONT, fontWeight: 700, textDecoration: "none" }}>Get Started Free</Link>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </nav>
  );
}

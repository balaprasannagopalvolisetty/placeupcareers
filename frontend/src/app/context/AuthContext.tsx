import { createContext, useContext, useEffect, useState } from "react";
import {
  clearStoredToken,
  logout as apiLogout,
  refreshAccessToken,
  signin,
  signup,
  verifyOtp,
  type AuthResponse,
  type SignupPayload,
  type SignupResult,
} from "../lib/api";

interface AuthUser {
  id?: string;
  first_name?: string;
  last_name?: string;
  email?: string;
  plan?: string;
}

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  isAuthenticated: boolean;
  signIn: (identifier: string, password: string) => Promise<void>;
  // Returns the raw result so the multi-step signup wizard can branch on
  // whether email verification (OTP) is still required.
  signUp: (payload: SignupPayload) => Promise<SignupResult>;
  // Completes signup after the user enters the emailed code.
  verifySignupOtp: (email: string, code: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const handleAuthCleared = () => {
      setUser(null);
      setLoading(false);
    };
    window.addEventListener("placeup:auth-cleared", handleAuthCleared);
    return () => window.removeEventListener("placeup:auth-cleared", handleAuthCleared);
  }, []);

  useEffect(() => {
    let active = true;

    async function loadProfile() {
      try {
        const session = await refreshAccessToken();
        if (active && session.user) {
          setUser(session.user);
        } else if (active) {
          clearStoredToken();
          setUser(null);
        }
      } catch (error) {
        clearStoredToken();
        setUser(null);
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    loadProfile();

    return () => {
      active = false;
    };
  }, []);

  const signIn = async (identifier: string, password: string) => {
    setLoading(true);
    try {
      const data = await signin(identifier, password);
      setUser({ id: data.user_id, first_name: data.first_name, last_name: data.last_name, email: data.email, plan: data.plan });
    } finally {
      setLoading(false);
    }
  };

  const applyAuth = (data: AuthResponse) => {
    setUser({ id: data.user_id, first_name: data.first_name, last_name: data.last_name, email: data.email, plan: data.plan });
  };

  const signUp = async (payload: SignupPayload): Promise<SignupResult> => {
    setLoading(true);
    try {
      const data = await signup(payload);
      // When no email verification is required the backend returns a session.
      const needsOtp = "otp_required" in data && data.otp_required === true;
      if (!needsOtp) {
        applyAuth(data as AuthResponse);
      }
      return data;
    } finally {
      setLoading(false);
    }
  };

  const verifySignupOtp = async (email: string, code: string) => {
    setLoading(true);
    try {
      const data = await verifyOtp(email, code, "signup");
      applyAuth(data);
    } finally {
      setLoading(false);
    }
  };

  const signOut = async () => {
    setUser(null);
    await apiLogout();
  };

  const value: AuthContextValue = {
    user,
    loading,
    isAuthenticated: Boolean(user),
    signIn,
    signUp,
    verifySignupOtp,
    signOut,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}

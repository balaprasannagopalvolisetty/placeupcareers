import { createContext, useContext, useEffect, useState } from "react";
import {
  clearStoredToken,
  getSession,
  logout as apiLogout,
  refreshAccessToken,
  signin,
  signup,
  type SignupPayload,
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
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (payload: SignupPayload) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;

    async function loadProfile() {
      try {
        await refreshAccessToken();
        const session = await getSession();
        if (active && session.authenticated && session.user) {
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

  const signIn = async (email: string, password: string) => {
    setLoading(true);
    try {
      const data = await signin(email, password);
      setUser({ id: data.user_id, first_name: data.first_name, last_name: data.last_name, email: data.email, plan: data.plan });
    } finally {
      setLoading(false);
    }
  };

  const signUp = async (payload: SignupPayload) => {
    setLoading(true);
    try {
      const data = await signup(payload);
      setUser({ id: data.user_id, first_name: data.first_name, last_name: data.last_name, email: data.email, plan: data.plan });
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

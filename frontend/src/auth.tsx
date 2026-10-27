import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { ApiError, getCurrentUser, type User } from "./api";

type AuthState =
  | { status: "loading"; user: null; error: "" }
  | { status: "authenticated"; user: User; error: "" }
  | { status: "unauthenticated"; user: null; error: "" }
  | { status: "error"; user: null; error: string };

type AuthContextValue = {
  state: AuthState;
  setUser: (user: User) => void;
  clearUser: () => void;
  refresh: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    status: "loading",
    user: null,
    error: "",
  });
  const authVersion = useRef(0);

  const refresh = useCallback(async () => {
    const version = authVersion.current;
    setState({ status: "loading", user: null, error: "" });
    try {
      const result = await getCurrentUser();
      if (version === authVersion.current) {
        setState({ status: "authenticated", user: result.user, error: "" });
      }
    } catch (cause) {
      if (version !== authVersion.current) return;
      if (cause instanceof ApiError && cause.status === 401) {
        setState({ status: "unauthenticated", user: null, error: "" });
      } else {
        setState({
          status: "error",
          user: null,
          error: cause instanceof Error ? cause.message : "Could not verify your session.",
        });
      }
    }
  }, []);

  useEffect(() => {
    void refresh();
    const onUnauthorized = () => {
      authVersion.current += 1;
      setState({ status: "unauthenticated", user: null, error: "" });
    };
    window.addEventListener("phishshift:unauthorized", onUnauthorized);
    return () => window.removeEventListener("phishshift:unauthorized", onUnauthorized);
  }, [refresh]);

  const setUser = useCallback((user: User) => {
    authVersion.current += 1;
    setState({ status: "authenticated", user, error: "" });
  }, []);
  const clearUser = useCallback(() => {
    authVersion.current += 1;
    setState({ status: "unauthenticated", user: null, error: "" });
  }, []);
  const value = useMemo(
    () => ({ state, setUser, clearUser, refresh }),
    [state, setUser, clearUser, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider.");
  return context;
}

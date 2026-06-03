import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useQueryClient } from "@tanstack/react-query";

import {
  AUTH_SESSION_EXPIRED_EVENT,
  clearAuthTokens,
  getMe,
  getStoredAccessToken,
  getStoredRefreshToken,
  isDevAuthFallbackEnabled,
  login,
  logout,
  refreshAuthToken,
  register,
  setAuthTokens,
  uploadCurrentUserAvatar,
  type AuthMeResponse,
  type AuthTokenResponse,
  type OrganizationSummary,
} from "../tasks/api";

export type AuthContextValue = {
  user: AuthMeResponse | null;
  loading: boolean;
  error: string | null;
  isUsingDevToken: boolean;
  currentOrganization: OrganizationSummary | null;
  reload: () => Promise<AuthMeResponse | null>;
  loginWithPassword: (payload: { email: string; password: string; organization_id?: string | null }) => Promise<AuthMeResponse>;
  registerWithPassword: (payload: {
    email: string;
    password: string;
    name: string;
    organization_name?: string | null;
  }) => Promise<AuthMeResponse>;
  logoutCurrentUser: () => Promise<void>;
  uploadAvatar: (file: File) => Promise<AuthMeResponse>;
  switchOrganization: (organizationId: string) => Promise<AuthMeResponse>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<AuthMeResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isUsingDevToken, setIsUsingDevToken] = useState(isDevAuthFallbackEnabled);

  const loadMe = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const next = await getMe();
      setUser(next);
      setIsUsingDevToken(isDevAuthFallbackEnabled());
      return next;
    } catch (loadError) {
      const message = loadError instanceof Error ? loadError.message : "无法加载当前用户";
      if (getStoredAccessToken()) {
        clearAuthTokens();
      }
      setIsUsingDevToken(isDevAuthFallbackEnabled());
      setError(message);
      setUser(null);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadMe();
  }, [loadMe]);

  useEffect(() => {
    const handleSessionExpired = () => {
      clearAuthTokens();
      setUser(null);
      setError("登录已过期，请重新登录");
      setIsUsingDevToken(isDevAuthFallbackEnabled());
      setLoading(false);
      void queryClient.invalidateQueries();
    };
    window.addEventListener(AUTH_SESSION_EXPIRED_EVENT, handleSessionExpired);
    return () => window.removeEventListener(AUTH_SESSION_EXPIRED_EVENT, handleSessionExpired);
  }, [queryClient]);

  const applyTokensAndLoad = useCallback(
    async (tokens: AuthTokenResponse) => {
      setAuthTokens(tokens);
      setIsUsingDevToken(false);
      const next = await loadMe();
      if (!next) {
        throw new Error("登录成功，但无法加载当前用户");
      }
      await queryClient.invalidateQueries();
      return next;
    },
    [loadMe, queryClient],
  );

  const value = useMemo<AuthContextValue>(() => {
    const currentOrganization =
      user?.organizations.find((org) => org.id === user.organization_id) ?? user?.organizations[0] ?? null;
    return {
      user,
      loading,
      error,
      isUsingDevToken,
      currentOrganization,
      reload: loadMe,
      loginWithPassword: async (payload) => applyTokensAndLoad(await login(payload)),
      registerWithPassword: async (payload) => applyTokensAndLoad(await register(payload)),
      logoutCurrentUser: async () => {
        try {
          await logout();
        } finally {
          clearAuthTokens();
          setIsUsingDevToken(isDevAuthFallbackEnabled());
          await loadMe();
          await queryClient.invalidateQueries();
        }
      },
      uploadAvatar: async (file) => {
        const next = await uploadCurrentUserAvatar(file);
        setUser(next);
        await queryClient.invalidateQueries();
        return next;
      },
      switchOrganization: async (organizationId) => {
        if (organizationId === user?.organization_id) {
          return user;
        }
        const refreshToken = getStoredRefreshToken();
        if (!refreshToken) {
          throw new Error("当前 dev-token 会话不支持工作区切换，请先登录。");
        }
        return applyTokensAndLoad(await refreshAuthToken(refreshToken, organizationId));
      },
    };
  }, [applyTokensAndLoad, error, isUsingDevToken, loadMe, loading, queryClient, user]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return value;
}

export function useOptionalAuth() {
  return useContext(AuthContext);
}

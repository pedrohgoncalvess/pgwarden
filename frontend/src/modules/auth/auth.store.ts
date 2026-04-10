import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { AuthResponse } from "@/modules/auth/auth.schema";

type AuthSession = {
  accessToken: string;
  refreshToken: string;
  tokenType: string;
  accessTokenExpiresAt: string;
  refreshTokenExpiresAt: string;
};

type AuthStore = {
  session: AuthSession | null;
  setSessionFromAuthResponse: (auth: AuthResponse) => void;
  clearSession: () => void;
};

function parseServerDateAsUtc(dateTime: string): number {
  const normalized = dateTime.trim().replace(" ", "T");
  return Date.parse(`${normalized}Z`);
}

export function getAccessTokenExpiresAtMs(session: AuthSession): number {
  return parseServerDateAsUtc(session.accessTokenExpiresAt);
}

export function isSessionExpired(session: AuthSession, nowMs = Date.now()): boolean {
  const expiresAtMs = getAccessTokenExpiresAtMs(session);
  if (Number.isNaN(expiresAtMs)) {
    return true;
  }
  return expiresAtMs <= nowMs;
}

export const useAuthStore = create<AuthStore>()(
  persist(
    (set) => ({
      session: null,
      setSessionFromAuthResponse: (auth) =>
        set({
          session: {
            accessToken: auth.access_token.token,
            refreshToken: auth.refresh_token.token,
            tokenType: auth.token_type,
            accessTokenExpiresAt: auth.access_token.expires,
            refreshTokenExpiresAt: auth.refresh_token.expires,
          },
        }),
      clearSession: () => set({ session: null }),
    }),
    {
      name: "pgwarden-auth-session",
      partialize: (state) => ({ session: state.session }),
    }
  )
);

export const authSelectors = {
  session: (state: AuthStore) => state.session,
  accessToken: (state: AuthStore) => state.session?.accessToken ?? null,
  isAuthenticated: (state: AuthStore) => {
    if (!state.session) {
      return false;
    }
    return !isSessionExpired(state.session);
  },
  setSessionFromAuthResponse: (state: AuthStore) => state.setSessionFromAuthResponse,
  clearSession: (state: AuthStore) => state.clearSession,
};

import { create } from 'zustand'

import type { User } from '@/types/auth'

interface AuthState {
  user: User | null
  /**
   * Short-lived JWT access token, kept in memory ONLY (never persisted to
   * localStorage/sessionStorage — SPEC NFR-2/C-5, skill 40-frontend-security-auth).
   * The refresh token lives in an httpOnly+Secure+SameSite=Lax cookie the
   * browser manages automatically; JS never sees it (FR-4).
   */
  accessToken: string | null
  isHydrating: boolean
  setSession: (user: User, accessToken: string) => void
  setAccessToken: (accessToken: string | null) => void
  clearSession: () => void
  setHydrating: (value: boolean) => void
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  accessToken: null,
  // true until the app has attempted a silent refresh on boot (see AuthBootstrap)
  isHydrating: true,
  setSession: (user, accessToken) => set({ user, accessToken, isHydrating: false }),
  setAccessToken: (accessToken) => set({ accessToken }),
  clearSession: () => set({ user: null, accessToken: null, isHydrating: false }),
  setHydrating: (value) => set({ isHydrating: value }),
}))

export const selectIsAuthenticated = (s: AuthState) => Boolean(s.user && s.accessToken)

// Stable reference for the "no user" case — `s.user?.roles ?? []` would return a
// *new* array on every call, and Zustand's useSyncExternalStore treats that as
// "the snapshot changed" on every render, causing an infinite render loop
// ("Maximum update depth exceeded") anywhere this selector is read before login.
const EMPTY_ROLES: User['roles'] = []
export const selectRoles = (s: AuthState) => s.user?.roles ?? EMPTY_ROLES

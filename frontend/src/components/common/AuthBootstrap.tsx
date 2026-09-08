import { useEffect, useRef, type ReactNode } from 'react'

import { authApi } from '@/api/auth'
import { useAuthStore } from '@/stores/authStore'

/**
 * Runs once on app boot: attempts a silent refresh against the httpOnly
 * refresh-token cookie (FR-4/FR-14) so a returning user with a valid session
 * doesn't have to log in again on every page load. Resolves `isHydrating`
 * either way so `ProtectedRoute` can stop showing a loading state.
 */
export function AuthBootstrap({ children }: { children: ReactNode }) {
  const setSession = useAuthStore((s) => s.setSession)
  const clearSession = useAuthStore((s) => s.clearSession)
  const ranOnce = useRef(false)

  useEffect(() => {
    if (ranOnce.current) return
    ranOnce.current = true

    let cancelled = false

    async function bootstrap() {
      try {
        const { access } = await authApi.refresh()
        useAuthStore.getState().setAccessToken(access)
        const user = await authApi.me()
        if (!cancelled) setSession(user, access)
      } catch {
        if (!cancelled) clearSession()
      }
    }

    void bootstrap()
    return () => {
      cancelled = true
    }
  }, [setSession, clearSession])

  return children
}

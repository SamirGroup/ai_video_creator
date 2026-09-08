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
    // Guards against React 19 StrictMode's dev-only double-invoke of effects:
    // mount -> cleanup -> mount. `ranOnce` is a ref, so it survives that
    // synthetic cleanup/remount (refs aren't reset by it, only effects are).
    // The second invocation short-circuits here and never runs bootstrap()
    // again, so the *first* invocation's request is the only one in flight
    // and must be allowed to resolve normally — an earlier version tracked a
    // `cancelled` flag flipped by this same effect's cleanup, which fired
    // right after the first mount (StrictMode's synthetic unmount) and so
    // permanently suppressed `setSession`/`clearSession` on the real
    // response, leaving `isHydrating` stuck `true` forever (every route
    // behind `ProtectedRoute` stayed on its loading state indefinitely).
    if (ranOnce.current) return
    ranOnce.current = true

    async function bootstrap() {
      try {
        const { access } = await authApi.refresh()
        useAuthStore.getState().setAccessToken(access)
        const user = await authApi.me()
        setSession(user, access)
      } catch {
        clearSession()
      }
    }

    void bootstrap()
  }, [setSession, clearSession])

  return children
}

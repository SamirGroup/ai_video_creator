import { Navigate, Outlet, useLocation } from 'react-router-dom'

import { PageLoading } from '@/components/common/StateViews'
import { useAuth } from '@/hooks/useAuth'

/**
 * Guards creator/admin routes: unauthenticated users are redirected to
 * `/login` (401-equivalent at the router level) with the original location
 * preserved so we can send them back after signing in.
 */
export function ProtectedRoute() {
  const { isAuthenticated, isHydrating } = useAuth()
  const location = useLocation()

  if (isHydrating) {
    return <PageLoading />
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />
  }

  return <Outlet />
}

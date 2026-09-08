import { Outlet } from 'react-router-dom'

import { ForbiddenState } from '@/components/common/StateViews'
import { useAuth } from '@/hooks/useAuth'
import type { RoleCode } from '@/types/common'

/**
 * Client-side role gating is UX only (skill 40-frontend-security-auth) — the
 * server is the real authority and must reject unauthorized requests
 * regardless of what this component renders. This just avoids showing staff
 * screens to creators (and vice versa).
 */
export function RoleRoute({ allow }: { allow: RoleCode[] }) {
  const { hasAnyRole, isHydrating } = useAuth()

  if (isHydrating) return null
  if (!hasAnyRole(allow)) return <ForbiddenState />

  return <Outlet />
}

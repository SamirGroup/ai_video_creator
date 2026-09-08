import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'

import { authApi } from '@/api/auth'
import { selectIsAuthenticated, selectRoles, useAuthStore } from '@/stores/authStore'
import type { RoleCode } from '@/types/common'

export function useAuth() {
  const user = useAuthStore((s) => s.user)
  const isAuthenticated = useAuthStore(selectIsAuthenticated)
  const roles = useAuthStore(selectRoles)
  const isHydrating = useAuthStore((s) => s.isHydrating)
  const clearSession = useAuthStore((s) => s.clearSession)
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const logoutMutation = useMutation({
    mutationFn: () => authApi.logout(),
    onSettled: () => {
      clearSession()
      queryClient.clear()
      navigate('/login', { replace: true })
    },
  })

  const hasRole = (role: RoleCode) => roles.includes(role)
  const hasAnyRole = (allowed: RoleCode[]) => allowed.some((r) => roles.includes(r))

  return {
    user,
    roles,
    isAuthenticated,
    isHydrating,
    hasRole,
    hasAnyRole,
    logout: logoutMutation.mutate,
    isLoggingOut: logoutMutation.isPending,
  }
}

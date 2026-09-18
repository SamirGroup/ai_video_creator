import { Navigate, useParams } from 'react-router-dom'
import { DashboardPage } from '@/pages/creator/DashboardPage'
import { useAuthStore } from '@/stores/authStore'
import { homePath } from './homePath'

export function CreatorHomeRoute() {
  const { id } = useParams()
  const user = useAuthStore((s) => s.user)
  if (!user) return <Navigate to="/login" replace />
  if (id !== user.id || !user.roles.includes('creator')) return <Navigate to={homePath(user)} replace />
  return <DashboardPage />
}

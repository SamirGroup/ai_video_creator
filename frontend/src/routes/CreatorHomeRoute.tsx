import { useQuery } from '@tanstack/react-query'
import { assistantApi } from '@/api/assistant'
import { Navigate, useParams } from 'react-router-dom'
import { DashboardPage } from '@/pages/creator/DashboardPage'
import { useAuthStore } from '@/stores/authStore'
import { homePath } from './homePath'

export function CreatorHomeRoute() {
  const { id } = useParams()
  const user = useAuthStore((s) => s.user)
  const profile = useQuery({
    queryKey: ['assistant'],
    queryFn: assistantApi.state,
    enabled: !!user?.roles.includes('creator') && id === user.id,
  })
  if (!user) return <Navigate to="/login" replace />
  if (id !== user.id || !user.roles.includes('creator'))
    return <Navigate to={homePath(user)} replace />
  if (profile.isPending)
    return <div className="p-6 text-muted-foreground">Yuklanmoqda…</div>
  if (profile.data && !profile.data.profile.onboarding_completed)
    return <Navigate to="/assistant" replace />
  return <DashboardPage />
}

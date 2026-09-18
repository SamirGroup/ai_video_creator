import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { adminNavItems } from '@/components/layout/navConfig'
import { useAuth } from '@/hooks/useAuth'

export function AdminDashboardPage() {
  const { t } = useTranslation()
  const { hasAnyRole } = useAuth()
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">Admin dashboard</h1>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {adminNavItems.filter((item) => !item.roles || hasAnyRole(item.roles)).map((item) => (
          <Link key={item.to} to={item.to} className="rounded-lg border border-border bg-surface p-5 hover:bg-muted">
            {t(item.labelKey)} →
          </Link>
        ))}
      </div>
    </div>
  )
}

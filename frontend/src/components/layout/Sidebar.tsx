import { Sparkles } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { NavLink } from 'react-router-dom'

import { adminNavItems, creatorNavItems, STAFF_ROLES, NavIcon } from './navConfig'
import { useAuth } from '@/hooks/useAuth'
import { cn } from '@/lib/cn'
import { useUiStore } from '@/stores/uiStore'

export function Sidebar() {
  const { t } = useTranslation()
  const { hasAnyRole, user } = useAuth()
  const isSidebarOpen = useUiStore((s) => s.isSidebarOpen)
  const setSidebarOpen = useUiStore((s) => s.setSidebarOpen)
  const isStaff = hasAnyRole(STAFF_ROLES)

  const linkClasses = ({ isActive }: { isActive: boolean }) =>
    cn(
      'studio-nav-link flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors',
      'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-surface',
      isActive
        ? 'bg-primary-50 text-primary-700 dark:bg-primary-900/40 dark:text-primary-200'
        : 'text-muted-foreground hover:bg-muted hover:text-foreground',
    )

  return (
    <>
      {/* Mobile overlay */}
      {isSidebarOpen && (
        <button
          type="button"
          aria-hidden="true"
          tabIndex={-1}
          onClick={() => setSidebarOpen(false)}
          className="fixed inset-0 z-30 bg-black/40 lg:hidden"
        />
      )}
      <aside
        aria-label={t('nav.primary')}
        className={cn(
          'dashboard-sidebar flex flex-col fixed inset-y-0 start-0 z-40 w-64 shrink-0 border-e border-border bg-surface transition-transform lg:sticky lg:top-0 lg:h-svh lg:translate-x-0',
          isSidebarOpen ? 'translate-x-0' : '-translate-x-full rtl:translate-x-full',
        )}
      >
        <div className="flex h-14 shrink-0 items-center gap-3 border-b border-border px-4">
          <span className="studio-brand-mark">
            <Sparkles size={20} aria-hidden="true" />
          </span>
          <span className="text-sm font-semibold text-foreground">{t('app.name')}</span>
        </div>
        <nav className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto p-3">
          {user?.roles.includes('creator') &&
            creatorNavItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to === '/dashboard' ? `/creator/${user.id}` : item.to}
                className={linkClasses}
                onClick={() => setSidebarOpen(false)}
              >
                <span className="studio-nav-icon">
                  <NavIcon to={item.to} />
                </span>
                {t(item.labelKey)}
              </NavLink>
            ))}

          {isStaff && (
            <>
              <p className="mt-4 px-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {t('nav.adminSection')}
              </p>
              {user?.roles.includes('admin') && (
                <NavLink
                  to="/admin-dashboard"
                  className={linkClasses}
                  onClick={() => setSidebarOpen(false)}
                >
                  <span className="studio-nav-icon">
                    <NavIcon to="/admin-dashboard" />
                  </span>
                  {t('nav.adminDashboard')}
                </NavLink>
              )}
              {adminNavItems
                .filter((item) => !item.roles || hasAnyRole(item.roles))
                .map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    className={linkClasses}
                    onClick={() => setSidebarOpen(false)}
                  >
                    <span className="studio-nav-icon">
                      <NavIcon to={item.to} />
                    </span>
                    {t(item.labelKey)}
                  </NavLink>
                ))}
            </>
          )}
        </nav>
        <div className="studio-sidebar-footer">
          <span className="studio-avatar" aria-hidden="true">
            {(user?.full_name || user?.email || 'C').slice(0, 2).toUpperCase()}
          </span>
          <div className="min-w-0">
            <p className="truncate text-xs font-semibold">
              {user?.full_name || user?.email}
            </p>
            <p className="mt-1 text-[10px] text-muted-foreground">
              {isStaff ? 'Admin workspace' : 'Creator workspace'}
            </p>
          </div>
        </div>
      </aside>
    </>
  )
}

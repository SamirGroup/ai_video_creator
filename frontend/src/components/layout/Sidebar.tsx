import { useTranslation } from 'react-i18next'
import { NavLink } from 'react-router-dom'

import { adminNavItems, creatorNavItems, STAFF_ROLES } from './navConfig'
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
      'flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors',
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
        aria-label="Primary"
        className={cn(
          'dashboard-sidebar fixed inset-y-0 start-0 z-40 w-64 shrink-0 border-e border-border bg-surface transition-transform lg:sticky lg:top-0 lg:h-svh lg:translate-x-0',
          isSidebarOpen ? 'translate-x-0' : '-translate-x-full rtl:translate-x-full',
        )}
      >
        <div className="flex h-14 items-center gap-2 border-b border-border px-4">
          <span className="text-sm font-semibold text-foreground">{t('app.name')}</span>
        </div>
        <nav className="flex flex-col gap-1 overflow-y-auto p-3">
          {user?.roles.includes('creator') && creatorNavItems.map((item) => (
            <NavLink key={item.to} to={item.to === '/dashboard' ? `/creator/${user.id}` : item.to} className={linkClasses}>
              <span className="nav-dot" aria-hidden="true" />
              {t(item.labelKey)}
            </NavLink>
          ))}

          {isStaff && (
            <>
              <p className="mt-4 px-3 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Admin
              </p>
              {user?.roles.includes('admin') && (
                <NavLink to="/admin-dashboard" className={linkClasses}>
                  <span className="nav-dot" aria-hidden="true" />
                  Admin dashboard
                </NavLink>
              )}
              {adminNavItems
                .filter((item) => !item.roles || hasAnyRole(item.roles))
                .map((item) => (
                  <NavLink key={item.to} to={item.to} className={linkClasses}>
                    <span className="nav-dot" aria-hidden="true" />
                    {t(item.labelKey)}
                  </NavLink>
                ))}
            </>
          )}
        </nav>
      </aside>
    </>
  )
}

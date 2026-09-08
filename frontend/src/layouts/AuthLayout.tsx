import { Outlet } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

import { LanguageSwitcher } from '@/components/layout/LanguageSwitcher'
import { OfflineBanner } from '@/components/layout/OfflineBanner'

/** Shell for public auth screens (login/register/verify-email/forgot-password). */
export function AuthLayout() {
  const { t } = useTranslation()

  return (
    <div className="flex min-h-svh flex-col bg-background">
      <OfflineBanner />
      <header className="flex items-center justify-between px-4 py-4 sm:px-8">
        <span className="text-sm font-semibold text-foreground">{t('app.name')}</span>
        <LanguageSwitcher />
      </header>
      <main className="flex flex-1 items-center justify-center px-4 pb-16">
        <div className="w-full max-w-sm animate-fade-in">
          <Outlet />
        </div>
      </main>
    </div>
  )
}

import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { billingApi } from '@/api/billing'
import { VideoModelCatalog } from '@/components/common/VideoModelCatalog'
import { ThemeToggle } from '@/components/layout/ThemeToggle'
import { LanguageSwitcher } from '@/components/layout/LanguageSwitcher'
import { ErrorState } from '@/components/common/StateViews'

export function PricingPage() {
  const { t } = useTranslation()
  const plans = useQuery({ queryKey: ['plans'], queryFn: billingApi.listPlans })
  return (
    <div className="dashboard-shell min-h-svh bg-background text-foreground">
      <main className="mx-auto max-w-7xl space-y-8 p-5 sm:p-10">
        <header className="flex flex-wrap items-center justify-between gap-4">
          <Link to="/" className="text-xl font-semibold">
            CreatorAI
          </Link>
          <div className="flex items-center gap-3">
            <LanguageSwitcher />
            <ThemeToggle />
            <Link to="/billing">{t('billing.title', 'Billing')}</Link>
          </div>
        </header>
        <h1 className="text-3xl font-semibold">{t('billing.plans', 'Plans')}</h1>
        {plans.isError && <ErrorState />}
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {plans.data
            ?.filter((p) => p.ai_budget_enabled)
            .map((p) => (
              <article
                key={p.id}
                className="space-y-4 rounded-2xl border border-border bg-surface p-6"
              >
                <h2 className="text-xl font-semibold">{p.name}</h2>
                <p className="text-3xl font-bold">
                  ${p.quote?.net ?? p.price_amount}
                  <span className="text-sm font-normal">
                    {' '}
                    / {t('planning.monthly', 'Monthly')}
                  </span>
                </p>
                <p>
                  {t('billing.tax', 'Tax')}: ${p.quote?.tax} ·{' '}
                  {t('billing.total', 'Total')}: ${p.quote?.total}
                </p>
                <p>
                  AI: ${p.quote?.ai_budget_usd} · {p.quote?.ai_credits.toLocaleString()}{' '}
                  {t('billing.credits', 'credits')}
                </p>
                <Link
                  className="inline-block rounded-xl bg-primary-600 px-5 py-3 text-white"
                  to="/billing"
                >
                  {t('billing.choosePlan', 'Choose plan')}
                </Link>
              </article>
            ))}
        </div>
        <VideoModelCatalog />
      </main>
    </div>
  )
}

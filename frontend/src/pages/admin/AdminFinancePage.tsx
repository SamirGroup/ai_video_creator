import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { CardSkeletonGrid, ErrorState } from '@/components/common/StateViews'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { mockFinanceOverview } from '@/mocks/fixtures'
import { mockFetch } from '@/mocks/mockFetch'
import { adminApi } from '@/api/admin'

// TODO: real API — replace with adminApi.financeOverview() (src/api/admin.ts)
function useFinanceOverview() {
  return useQuery({
    queryKey: ['admin-finance-overview'],
    queryFn: () => mockFetch(mockFinanceOverview),
  })
}

function formatCurrency(amount: string, currency: string, locale: string) {
  return new Intl.NumberFormat(locale, { style: 'currency', currency }).format(Number(amount))
}

export function AdminFinancePage() {
  const { t, i18n } = useTranslation()
  const { data, isLoading, isError, refetch } = useFinanceOverview()
  const locale = i18n.resolvedLanguage ?? 'en'

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold text-foreground">{t('admin.finance.title')}</h1>
        {/* TODO: real API — GET /admin/finance/export (CSV/XLSX, SPEC FR-73) */}
        <a
          href={adminApi.financeExportUrl()}
          className="inline-flex h-8 items-center rounded-md border border-border px-3 text-sm font-medium text-foreground transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
        >
          {t('admin.finance.export')}
        </a>
      </div>

      {isLoading && <CardSkeletonGrid />}
      {isError && <ErrorState onRetry={() => refetch()} />}

      {data && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Card>
            <CardHeader>
              <CardTitle>{t('admin.finance.mrr')}</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-semibold text-foreground">
                {formatCurrency(data.mrr, data.currency, locale)}
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{t('admin.finance.activeSubscriptions')}</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-semibold text-foreground">{data.active_subscriptions}</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{t('admin.finance.revenueShareTotal')}</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-semibold text-foreground">
                {formatCurrency(data.revenue_share_total, data.currency, locale)}
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{t('admin.finance.uncollected')}</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-semibold text-foreground">
                {formatCurrency(data.uncollected_invoices_total, data.currency, locale)}
              </p>
              <p className="text-xs text-muted-foreground">
                {data.uncollected_invoices_count} {t('admin.finance.title')}
              </p>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}

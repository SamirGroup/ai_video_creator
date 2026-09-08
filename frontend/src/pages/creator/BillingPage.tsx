import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { CardSkeletonGrid, ErrorState, TableSkeleton } from '@/components/common/StateViews'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { mockInvoices, mockSubscription } from '@/mocks/fixtures'
import { mockFetch } from '@/mocks/mockFetch'
import type { InvoiceStatus, SubscriptionStatus } from '@/types/billing'

// TODO: real API — replace with billingApi.mySubscription/listInvoices (src/api/billing.ts)
function useSubscription() {
  return useQuery({ queryKey: ['subscription'], queryFn: () => mockFetch(mockSubscription) })
}
function useInvoices() {
  return useQuery({ queryKey: ['invoices'], queryFn: () => mockFetch(mockInvoices) })
}

const subscriptionTone: Record<SubscriptionStatus, 'success' | 'warning' | 'destructive' | 'neutral'> = {
  trialing: 'neutral',
  active: 'success',
  past_due: 'warning',
  suspended: 'destructive',
  canceled: 'neutral',
  expired: 'destructive',
}

const invoiceTone: Record<InvoiceStatus, 'success' | 'warning' | 'destructive' | 'neutral'> = {
  draft: 'neutral',
  open: 'warning',
  paid: 'success',
  failed: 'destructive',
  void: 'neutral',
  uncollectible: 'destructive',
}

export function BillingPage() {
  const { t, i18n } = useTranslation()
  const subscriptionQuery = useSubscription()
  const invoicesQuery = useInvoices()

  const currencyFmt = (value: string) =>
    new Intl.NumberFormat(i18n.resolvedLanguage ?? 'en', { style: 'currency', currency: 'USD' }).format(
      Number(value),
    )

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold text-foreground">{t('billing.title')}</h1>

      {subscriptionQuery.isLoading && <CardSkeletonGrid count={1} />}
      {subscriptionQuery.isError && <ErrorState onRetry={() => subscriptionQuery.refetch()} />}

      {subscriptionQuery.data && (
        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <CardTitle className="text-base font-semibold text-foreground">
              {t('billing.currentPlan')}: {subscriptionQuery.data.plan.name}
            </CardTitle>
            <Badge tone={subscriptionTone[subscriptionQuery.data.status]} dot>
              {t(`billing.status.${subscriptionQuery.data.status}`)}
            </Badge>
          </CardHeader>
          <CardContent className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-muted-foreground">
              {currencyFmt(subscriptionQuery.data.plan.price_amount)} /{' '}
              {subscriptionQuery.data.plan.billing_interval === 'month' ? 'mo' : '6mo'}
            </p>
            <div className="flex gap-2">
              {/* TODO: real API — POST /billing/checkout-session (FR-22) */}
              <Button size="sm" variant="outline">
                {t('billing.changePlan')}
              </Button>
              {/* TODO: real API — POST /billing/portal-session (Stripe Customer Portal) */}
              <Button size="sm" variant="outline">
                {t('billing.managePayment')}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      <div>
        <h2 className="mb-3 text-sm font-semibold text-foreground">{t('billing.invoices')}</h2>
        {invoicesQuery.isLoading && <TableSkeleton rows={3} />}
        {invoicesQuery.isError && <ErrorState onRetry={() => invoicesQuery.refetch()} />}
        {invoicesQuery.data && (
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full min-w-[480px] text-left text-sm">
              <tbody className="divide-y divide-border">
                {invoicesQuery.data.map((invoice) => (
                  <tr key={invoice.id}>
                    <td className="px-4 py-3 text-foreground">{invoice.kind}</td>
                    <td className="px-4 py-3 text-foreground">{currencyFmt(invoice.amount)}</td>
                    <td className="px-4 py-3">
                      <Badge tone={invoiceTone[invoice.status]} dot>
                        {invoice.status}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

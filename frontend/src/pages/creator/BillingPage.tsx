import { useMutation, useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import {
  CardSkeletonGrid,
  ErrorState,
  TableSkeleton,
} from '@/components/common/StateViews'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { billingApi } from '@/api/billing'
import type { InvoiceStatus, SubscriptionStatus } from '@/types/billing'

// TODO: real API — replace with billingApi.mySubscription/listInvoices (src/api/billing.ts)
function useSubscription() {
  return useQuery({ queryKey: ['subscription'], queryFn: billingApi.mySubscription })
}
function useInvoices() {
  return useQuery({ queryKey: ['invoices'], queryFn: billingApi.listInvoices })
}

const subscriptionTone: Record<
  SubscriptionStatus,
  'success' | 'warning' | 'destructive' | 'neutral'
> = {
  trialing: 'neutral',
  active: 'success',
  past_due: 'warning',
  suspended: 'destructive',
  canceled: 'neutral',
  expired: 'destructive',
}

const invoiceTone: Record<
  InvoiceStatus,
  'success' | 'warning' | 'destructive' | 'neutral'
> = {
  draft: 'neutral',
  open: 'warning',
  paid: 'success',
  failed: 'destructive',
  void: 'neutral',
  uncollectible: 'destructive',
}

export function BillingPage() {
  const { t, i18n } = useTranslation()
  const plans = useQuery({ queryKey: ['plans'], queryFn: billingApi.listPlans })
  const checkout = useMutation({
    mutationFn: billingApi.createCheckoutSession,
    onSuccess: (data) => window.location.assign(data.checkout_url),
  })
  const paymentSetup = useMutation({
    mutationFn: billingApi.setupPayment,
    onSuccess: (data) => window.location.assign(data.checkout_url),
  })
  const portal = useMutation({
    mutationFn: billingApi.createPortalSession,
    onSuccess: (data) => window.location.assign(data.portal_url),
  })
  const subscriptionQuery = useSubscription()
  const invoicesQuery = useInvoices()

  const currencyFmt = (value: string) =>
    new Intl.NumberFormat(i18n.resolvedLanguage ?? 'en', {
      style: 'currency',
      currency: 'USD',
    }).format(Number(value))

  return (
    <div className="flex flex-col gap-6">
      <Button onClick={() => paymentSetup.mutate()} isLoading={paymentSetup.isPending}>
        {t('billing.managePayment')}
      </Button>
      <h1 className="text-xl font-semibold text-foreground">{t('billing.title')}</h1>

      {subscriptionQuery.isLoading && <CardSkeletonGrid count={1} />}
      {subscriptionQuery.isError && (
        <ErrorState onRetry={() => subscriptionQuery.refetch()} />
      )}

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
              <Button
                size="sm"
                variant="outline"
                onClick={() =>
                  document.getElementById('plans')?.scrollIntoView({ behavior: 'smooth' })
                }
              >
                {t('billing.changePlan')}
              </Button>
              {/* TODO: real API — POST /billing/portal-session (Stripe Customer Portal) */}
              <Button
                size="sm"
                variant="outline"
                isLoading={portal.isPending}
                onClick={() => portal.mutate()}
              >
                {t('billing.managePayment')}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {(checkout.isError || portal.isError || plans.isError || paymentSetup.isError) && (
        <ErrorState />
      )}
      <div id="plans" className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {plans.data?.map((plan) => (
          <Card key={plan.id}>
            <CardHeader>
              <CardTitle>{plan.name}</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="mb-3 text-2xl">{currencyFmt(plan.price_amount)}</p>
              <p className="mb-4 text-sm text-muted-foreground">
                {plan.videos_per_period} {t('channel.videos')}
              </p>
              <Button
                disabled={
                  plan.code === 'free' || subscriptionQuery.data?.plan.id === plan.id
                }
                isLoading={checkout.isPending}
                onClick={() => checkout.mutate(plan.code)}
              >
                {t('billing.changePlan')}
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
      <div>
        <h2 className="mb-3 text-sm font-semibold text-foreground">
          {t('billing.invoices')}
        </h2>
        {invoicesQuery.isLoading && <TableSkeleton rows={3} />}
        {invoicesQuery.isError && <ErrorState onRetry={() => invoicesQuery.refetch()} />}
        {invoicesQuery.data && (
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full min-w-[480px] text-start text-sm">
              <tbody className="divide-y divide-border">
                {invoicesQuery.data.map((invoice) => (
                  <tr key={invoice.id}>
                    <td className="px-4 py-3 text-foreground">{invoice.kind}</td>
                    <td className="px-4 py-3 text-foreground">
                      {currencyFmt(invoice.amount)}
                    </td>
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

import { apiClient } from '@/api/client'
import { isTelegram } from '@/components/common/TelegramBridge'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
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
  const telegram = isTelegram()
  const queryClient = useQueryClient()
  const linkCode = useMutation({
    mutationFn: () => apiClient.post<{ url: string }>('/telegram/link-code'),
    onSuccess: ({ data }) => window.location.assign(data.url),
  })
  const link = useMutation({
    mutationFn: () =>
      apiClient.post('/telegram/link', { init_data: window.Telegram?.WebApp.initData }),
  })
  const stars = useMutation({
    mutationFn: (plan_code: string) =>
      apiClient.post<{ invoice_url: string }>('/telegram/checkout', { plan_code }),
    onSuccess: ({ data }) =>
      window.Telegram?.WebApp.openInvoice(data.invoice_url, (status) => {
        if (status === 'paid') void queryClient.invalidateQueries()
      }),
  })
  const wallet = useQuery({
    queryKey: ['ai-wallet'],
    queryFn: () =>
      apiClient
        .get<{ available_usd: string; reserved_usd: string }>('/me/ai-wallet')
        .then((r) => r.data),
  })
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
      {!telegram && (
        <Button onClick={() => paymentSetup.mutate()} isLoading={paymentSetup.isPending}>
          {t('billing.managePayment')}
        </Button>
      )}
      {!telegram && (
        <Button onClick={() => linkCode.mutate()} isLoading={linkCode.isPending}>
          Connect Telegram bot / Mini App
        </Button>
      )}
      {telegram && (
        <Button onClick={() => link.mutate()} isLoading={link.isPending}>
          Link this Telegram account
        </Button>
      )}
      {(link.isError || stars.isError || linkCode.isError) && <ErrorState />}
      {link.isSuccess && <p role="status">Telegram linked</p>}
      {wallet.data && (
        <p>
          AI balance: ${wallet.data.available_usd} · Reserved: ${wallet.data.reserved_usd}
        </p>
      )}
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
              <Button
                size="sm"
                variant="outline"
                onClick={() =>
                  document.getElementById('plans')?.scrollIntoView({ behavior: 'smooth' })
                }
              >
                {t('billing.changePlan')}
              </Button>
              <Button
                size="sm"
                variant="outline"
                isLoading={portal.isPending}
                disabled={telegram}
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
              {plan.quote && (
                <div className="mb-4 space-y-1 text-sm">
                  <p>
                    {plan.discount_label}{' '}
                    {Number(plan.quote.discount_pct) > 0
                      ? `−${plan.quote.discount_pct}%`
                      : ''}
                  </p>
                  <p>
                    Tax: ${plan.quote.tax} · Total: ${plan.quote.total}
                  </p>
                  <p>
                    AI: ${plan.quote.ai_budget_usd} (
                    {plan.quote.ai_credits.toLocaleString()} credits)
                  </p>
                  <p>Platform: ${plan.quote.platform_usd}</p>
                  <p>{((plan.features?.video_models as string[]) ?? []).join(', ')}</p>
                  <p>
                    Usage depends on model, seconds, text tokens and audio. 1 credit =
                    $0.0001.
                  </p>
                  {telegram && <p>{plan.stars_amount || 'Not configured'} Stars</p>}
                </div>
              )}
              <Button
                disabled={
                  plan.code === 'free' || subscriptionQuery.data?.plan.id === plan.id
                }
                isLoading={checkout.isPending}
                onClick={() =>
                  telegram ? stars.mutate(plan.code) : checkout.mutate(plan.code)
                }
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

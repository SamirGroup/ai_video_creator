import { NumberPriceBreakdown } from '@/components/common/NumberPriceBreakdown'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { MessageSquare, Phone, ShieldCheck } from 'lucide-react'
import { virtualNumbersApi as api, type NumberOrder } from '@/api/virtualNumbers'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'

const card = 'rounded-xl border border-border bg-surface p-5'

function Rental({ order }: { order: NumberOrder }) {
  const { t } = useTranslation()
  const client = useQueryClient()
  const [opened, setOpened] = useState(false)
  const [reason, setReason] = useState('')
  const active =
    ['active', 'refund_requested'].includes(order.status) &&
    !!order.expires_at &&
    new Date(order.expires_at) > new Date()
  const inbox = useQuery({
    queryKey: ['number-inbox', order.id],
    queryFn: () => api.messages(order.id),
    enabled: opened && active,
    refetchInterval: opened && active ? 10000 : false,
    gcTime: 0,
  })
  const capture = useMutation({
    mutationFn: () => api.capturePayPal(order.id),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['number-orders'] })
    },
  })
  const returnedFromPayPal =
    new URLSearchParams(window.location.search).get('paypal_order') === order.id
  const attemptedReturn = useRef(false)
  useEffect(() => {
    if (
      returnedFromPayPal &&
      order.status === 'pending' &&
      order.payment_provider === 'paypal' &&
      !attemptedReturn.current
    ) {
      attemptedReturn.current = true
      capture.mutate()
    }
  }, [returnedFromPayPal, order.status, order.payment_provider, capture])
  const refund = useMutation({
    mutationFn: () => api.requestRefund(order.id, reason),
    onSuccess: () => {
      setReason('')
      void client.invalidateQueries({ queryKey: ['number-orders'] })
    },
  })
  return (
    <article className={card}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-semibold">{order.offer_name}</h3>
          <p className="text-sm text-muted-foreground">
            {order.service} · ${order.price_usd} ·{' '}
            {t(`numbers.status.${order.status}`, order.status)}
          </p>
        </div>
        {order.number && (
          <strong className="text-xl tracking-wide">{order.number}</strong>
        )}
      </div>
      <NumberPriceBreakdown price={order.price_breakdown} />
      {order.status === 'pending' && order.payment_provider === 'paypal' && (
        <div className="mt-3 space-y-2">
          <Button
            variant="outline"
            isLoading={capture.isPending}
            onClick={() => capture.mutate()}
          >
            {t('numbers.rental.checkPayPal')}
          </Button>
          {capture.isError && <p role="alert">{capture.error.message}</p>}
          {capture.isSuccess && capture.data.status === 'pending' && (
            <p>{t('numbers.rental.paypalPending')}</p>
          )}
        </div>
      )}
      {order.expires_at && (
        <p className="mt-2 text-sm">
          {t('numbers.rental.expiresAt', {
            date: new Date(order.expires_at).toLocaleString(),
          })}
        </p>
      )}
      {order.checkout_url && (
        <a
          className="mt-3 inline-block text-primary-600 underline"
          href={order.checkout_url}
        >
          {t('numbers.rental.continuePayment')}
        </a>
      )}
      {active && (
        <Button className="mt-4" variant="outline" onClick={() => setOpened(!opened)}>
          <MessageSquare size={16} />
          {opened ? t('numbers.rental.closeInbox') : t('numbers.rental.openInbox')}
        </Button>
      )}
      {opened && active && (
        <div className="mt-4 space-y-3" aria-live="polite">
          {inbox.isPending && <p>{t('numbers.rental.inboxLoading')}</p>}
          {inbox.isError && (
            <p role="alert">
              {t('numbers.rental.inboxFailed')}{' '}
              <button onClick={() => void inbox.refetch()} className="underline">
                {t('common.retry')}
              </button>
            </p>
          )}
          {inbox.data?.length === 0 && (
            <p className="text-sm text-muted-foreground">
              {t('numbers.rental.inboxEmpty')}
            </p>
          )}
          {inbox.data?.map((sms) => (
            <div key={sms.id} className="rounded-lg bg-muted p-4">
              <p className="text-xs text-muted-foreground">
                {sms.sender} · {new Date(sms.received_at).toLocaleString()}
              </p>
              <p className="mt-2 whitespace-pre-wrap break-words">{sms.body}</p>
            </div>
          ))}
        </div>
      )}
      {['active', 'expired'].includes(order.status) && (
        <form
          className="mt-4 flex flex-wrap items-end gap-3"
          onSubmit={(e) => {
            e.preventDefault()
            refund.mutate()
          }}
        >
          <Input
            label={t('numbers.rental.refundLabel')}
            minLength={5}
            maxLength={500}
            required
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
          <Button variant="outline" type="submit" isLoading={refund.isPending}>
            {t('numbers.rental.refundSubmit')}
          </Button>
          {refund.isError && <p role="alert">{refund.error.message}</p>}
        </form>
      )}
    </article>
  )
}

export function VirtualNumbersPage() {
  const { t } = useTranslation()
  const catalog = useQuery({ queryKey: ['number-catalog'], queryFn: api.catalog })
  const orders = useQuery({
    queryKey: ['number-orders'],
    queryFn: api.orders,
    refetchInterval: 15000,
  })
  const [service, setService] = useState('all')
  const [country, setCountry] = useState('all')
  const [accepted, setAccepted] = useState(false)
  const [gateway, setGateway] = useState('')
  const methods = catalog.data?.payment_methods ?? []
  const selectedGateway = gateway || methods.find((m) => m.available)?.code || ''
  const keys = useRef<Record<string, string>>({})
  const client = useQueryClient()
  const purchase = useMutation({
    mutationFn: (id: string) => {
      const offer = catalog.data?.offers.find((o) => o.id === id)
      if (!offer || !selectedGateway) throw new Error(t('numbers.payment.selectFirst'))
      const key = `${id}:${selectedGateway}`
      keys.current[key] ??= crypto.randomUUID()
      return api.purchase(id, keys.current[key], selectedGateway, offer.price_usd)
    },
    onSuccess: (order, id) => {
      delete keys.current[`${id}:${selectedGateway}`]
      void client.invalidateQueries({ queryKey: ['number-orders'] })
      if (order.checkout_url) window.location.assign(order.checkout_url)
    },
  })
  const offers = catalog.data?.offers ?? []
  const countries = [
    ...new Map(offers.map((o) => [o.country_code, o.country_name])).entries(),
  ]
  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <header>
        <div className="mb-2 flex items-center gap-3">
          <Phone className="text-primary-600" />
          <h1 className="text-2xl font-semibold">{t('numbers.title')}</h1>
        </div>
        <p className="text-muted-foreground">{t('numbers.subtitle')}</p>
      </header>
      <section className={card}>
        <div className="flex items-start gap-3">
          <ShieldCheck className="shrink-0 text-primary-600" />
          <div>
            <h2 className="font-semibold">{t('numbers.terms.title')}</h2>
            <p className="mt-2 text-sm text-muted-foreground">{t('numbers.terms.p1')}</p>
            <p className="mt-2 text-sm text-muted-foreground">{t('numbers.terms.p2')}</p>
            <label className="mt-4 flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                checked={accepted}
                onChange={(e) => setAccepted(e.target.checked)}
              />
              {t('numbers.terms.consent')}
            </label>
          </div>
        </div>
      </section>
      {catalog.data && !catalog.data.sales_ready && (
        <p className="rounded-xl border border-border bg-muted p-4">
          {t('numbers.salesPending')}
        </p>
      )}
      <section className={card}>
        <h2 className="font-semibold">{t('numbers.payment.title')}</h2>
        <div className="mt-3 flex flex-wrap gap-4">
          {methods.map((method) => (
            <label key={method.code} className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                name="number-payment"
                value={method.code}
                disabled={!method.available || purchase.isPending}
                checked={selectedGateway === method.code}
                onChange={() => setGateway(method.code)}
              />
              {method.label}
              {!method.available
                ? t('numbers.payment.unavailable')
                : method.mode !== 'live'
                  ? t('numbers.payment.sandbox')
                  : ''}
            </label>
          ))}
        </div>
        <p className="mt-3 text-xs text-muted-foreground">{t('numbers.payment.note')}</p>
      </section>
      <div className="flex flex-wrap gap-3">
        <label>
          {t('numbers.filter.service')}{' '}
          <select
            className="rounded border border-border bg-surface p-2"
            value={service}
            onChange={(e) => setService(e.target.value)}
          >
            <option value="all">{t('numbers.filter.all')}</option>
            {['youtube', 'telegram', 'whatsapp', 'other'].map((s) => (
              <option key={s} value={s}>
                {s === 'other'
                  ? t('numbers.filter.otherService')
                  : s.charAt(0).toUpperCase() + s.slice(1)}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t('numbers.filter.country')}{' '}
          <select
            className="rounded border border-border bg-surface p-2"
            value={country}
            onChange={(e) => setCountry(e.target.value)}
          >
            <option value="all">{t('numbers.filter.all')}</option>
            {countries.map(([code, name]) => (
              <option key={code} value={code}>
                {name}
              </option>
            ))}
          </select>
        </label>
      </div>
      {catalog.isPending && <p>{t('numbers.catalog.loading')}</p>}
      {catalog.isError && (
        <p role="alert">
          {t('numbers.catalog.failed')}{' '}
          <button className="underline" onClick={() => void catalog.refetch()}>
            {t('common.retry')}
          </button>
        </p>
      )}
      {purchase.isError && <p role="alert">{purchase.error.message}</p>}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {offers
          .filter(
            (o) =>
              (service === 'all' || o.service === service) &&
              (country === 'all' || country === o.country_code),
          )
          .map((o) => (
            <article className={card} key={o.id}>
              <p className="text-xs uppercase tracking-wide text-muted-foreground">
                {o.country_name} · {o.service}
              </p>
              <h2 className="mt-2 text-lg font-semibold">{o.name}</h2>
              <p className="mt-2 text-sm text-muted-foreground">{o.description}</p>
              <p className="mt-4 text-2xl font-semibold">
                ${o.price_usd}
                <span className="text-sm font-normal text-muted-foreground">
                  {' '}
                  {t('numbers.offer.days', { days: o.rental_days })}
                </span>
              </p>
              <NumberPriceBreakdown price={o.price_breakdown} />
              <p className="my-3 text-sm">
                {o.number_type === 'mobile'
                  ? t('numbers.offer.mobile')
                  : t('numbers.offer.voip')}{' '}
                ·{' '}
                {o.unavailable_reason
                  ? t('numbers.offer.unavailable')
                  : t('numbers.offer.available', { available: o.available_count })}
              </p>
              <Button
                disabled={
                  !accepted ||
                  !!o.unavailable_reason ||
                  !methods.some((m) => m.code === selectedGateway && m.available)
                }
                isLoading={purchase.isPending}
                onClick={() => purchase.mutate(o.id)}
              >
                {t('numbers.offer.rent')}
              </Button>
            </article>
          ))}
      </div>
      {catalog.isSuccess &&
        !offers.some(
          (o) =>
            (service === 'all' || o.service === service) &&
            (country === 'all' || country === o.country_code),
        ) && <div className={card}>{t('numbers.offer.none')}</div>}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold">{t('numbers.orders.title')}</h2>
        {orders.isPending && <p>{t('numbers.orders.loading')}</p>}
        {orders.isError && <p role="alert">{t('numbers.orders.failed')}</p>}
        {orders.data?.length === 0 && (
          <p className="text-muted-foreground">{t('numbers.orders.empty')}</p>
        )}
        {orders.data?.map((o) => (
          <Rental key={o.id} order={o} />
        ))}
      </section>
    </div>
  )
}

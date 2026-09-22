import { NumberPriceBreakdown } from '@/components/common/NumberPriceBreakdown'
import { numberStatus } from '@/api/virtualNumbers'
import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { MessageSquare, Phone, ShieldCheck } from 'lucide-react'
import { virtualNumbersApi as api, type NumberOrder } from '@/api/virtualNumbers'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'

const card = 'rounded-xl border border-border bg-surface p-5'

function Rental({ order }: { order: NumberOrder }) {
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
            {numberStatus[order.status] ?? order.status}
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
            PayPal to‘lovini tekshirish
          </Button>
          {capture.isError && <p role="alert">{capture.error.message}</p>}
          {capture.isSuccess && capture.data.status === 'pending' && (
            <p>
              PayPal to‘lovi hali yakunlanmagan. PayPal sahifasida tasdiqlang yoki
              keyinroq tekshiring.
            </p>
          )}
        </div>
      )}
      {order.expires_at && (
        <p className="mt-2 text-sm">
          Ijara tugashi: {new Date(order.expires_at).toLocaleString()}
        </p>
      )}
      {order.checkout_url && (
        <a
          className="mt-3 inline-block text-primary-600 underline"
          href={order.checkout_url}
        >
          To‘lovni davom ettirish
        </a>
      )}
      {active && (
        <Button className="mt-4" variant="outline" onClick={() => setOpened(!opened)}>
          <MessageSquare size={16} />
          {opened ? 'SMS oynasini yopish' : 'SMSlarni ko‘rish'}
        </Button>
      )}
      {opened && active && (
        <div className="mt-4 space-y-3" aria-live="polite">
          {inbox.isPending && <p>SMSlar yuklanmoqda…</p>}
          {inbox.isError && (
            <p role="alert">
              SMSlarni yuklab bo‘lmadi.{' '}
              <button onClick={() => void inbox.refetch()} className="underline">
                Qayta urinish
              </button>
            </p>
          )}
          {inbox.data?.length === 0 && (
            <p className="text-sm text-muted-foreground">
              Hozircha SMS kelmagan. Oyna har 10 soniyada yangilanadi.
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
            label="Muammo bo‘lsa, qaytarish so‘rovi sababi"
            minLength={5}
            maxLength={500}
            required
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
          <Button variant="outline" type="submit" isLoading={refund.isPending}>
            Ko‘rib chiqishga yuborish
          </Button>
          {refund.isError && <p role="alert">{refund.error.message}</p>}
        </form>
      )}
    </article>
  )
}

export function VirtualNumbersPage() {
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
      if (!offer || !selectedGateway) throw new Error('To‘lov usulini tanlang.')
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
          <h1 className="text-2xl font-semibold">Virtual raqamlar</h1>
        </div>
        <p className="text-muted-foreground">
          Shaxsiy raqam ijarasi va SMSlar — bitta kabinetda.
        </p>
      </header>
      <section className={card}>
        <div className="flex items-start gap-3">
          <ShieldCheck className="shrink-0 text-primary-600" />
          <div>
            <h2 className="font-semibold">Xizmat shartlari</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Raqam belgilangan muddatga faqat sizga ajratiladi. Kodni tegishli ilovaga
              o‘zingiz kiritasiz. SMS kelishi va platformaning raqamni qabul qilishi
              kafolatlanmaydi. YouTube monetizatsiyasi alohida talablarga bog‘liq.
            </p>
            <p className="mt-2 text-sm text-muted-foreground">
              Ijara avtomatik uzaymaydi. Muddat tugashidan oldin hisobingizni o‘zingiz
              boshqaradigan raqamga ko‘chiring. SMSlar ko‘pi bilan 24 soat saqlanadi.
              Muammo bo‘lsa, buyurtmadan pul qaytarish so‘rovini yuboring.
            </p>
            <label className="mt-4 flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                checked={accepted}
                onChange={(e) => setAccepted(e.target.checked)}
              />
              Faqat o‘zimga tegishli hisoblar uchun foydalanaman va ijara shartlariga
              roziman.
            </label>
          </div>
        </div>
      </section>
      {catalog.data && !catalog.data.sales_ready && (
        <p className="rounded-xl border border-border bg-muted p-4">
          Xizmat tayyorlanmoqda. Provayder bilan shartnoma va SMS ulanishi yakunlangach
          sotuv ochiladi. Hozir to‘lov olinmaydi.
        </p>
      )}
      <section className={card}>
        <h2 className="font-semibold">To‘lov usuli</h2>
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
                ? ' — ulanish kutilmoqda'
                : method.mode !== 'live'
                  ? ' — sinov rejimi'
                  : ''}
            </label>
          ))}
        </div>
        <p className="mt-3 text-xs text-muted-foreground">
          To‘lovni tanlangan provayderning himoyalangan sahifasida bajarasiz.
        </p>
      </section>
      <div className="flex flex-wrap gap-3">
        <label>
          Xizmat{' '}
          <select
            className="rounded border border-border bg-surface p-2"
            value={service}
            onChange={(e) => setService(e.target.value)}
          >
            <option value="all">Barchasi</option>
            {['youtube', 'telegram', 'whatsapp', 'other'].map((s) => (
              <option key={s} value={s}>
                {s === 'other' ? 'Boshqa' : s.charAt(0).toUpperCase() + s.slice(1)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Davlat{' '}
          <select
            className="rounded border border-border bg-surface p-2"
            value={country}
            onChange={(e) => setCountry(e.target.value)}
          >
            <option value="all">Barchasi</option>
            {countries.map(([code, name]) => (
              <option key={code} value={code}>
                {name}
              </option>
            ))}
          </select>
        </label>
      </div>
      {catalog.isPending && <p>Katalog yuklanmoqda…</p>}
      {catalog.isError && (
        <p role="alert">
          Katalogni yuklab bo‘lmadi.{' '}
          <button className="underline" onClick={() => void catalog.refetch()}>
            Qayta urinish
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
                  / {o.rental_days} kun
                </span>
              </p>
              <NumberPriceBreakdown price={o.price_breakdown} />
              <p className="my-3 text-sm">
                {o.number_type === 'mobile' ? 'Mobil raqam' : 'VoIP raqam'} ·{' '}
                {o.unavailable_reason
                  ? 'Hozircha mavjud emas'
                  : `${o.available_count} ta mavjud`}
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
                Ijaraga olish
              </Button>
            </article>
          ))}
      </div>
      {catalog.isSuccess &&
        !offers.some(
          (o) =>
            (service === 'all' || o.service === service) &&
            (country === 'all' || country === o.country_code),
        ) && (
          <div className={card}>
            Bu tanlov uchun hozircha taklif yo‘q. Tasdiqlangan tariflar shu yerda paydo
            bo‘ladi.
          </div>
        )}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold">Mening raqamlarim va SMSlarim</h2>
        {orders.isPending && <p>Buyurtmalar yuklanmoqda…</p>}
        {orders.isError && <p role="alert">Buyurtmalarni yuklab bo‘lmadi.</p>}
        {orders.data?.length === 0 && (
          <p className="text-muted-foreground">Hali raqam ijaraga olinmagan.</p>
        )}
        {orders.data?.map((o) => (
          <Rental key={o.id} order={o} />
        ))}
      </section>
    </div>
  )
}

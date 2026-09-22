import { NumberPriceBreakdown } from '@/components/common/NumberPriceBreakdown'
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { virtualNumbersApi as api, type NumberOffer } from '@/api/virtualNumbers'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { numberStatus } from '@/api/virtualNumbers'

const empty = {
  name: '',
  country_code: '',
  country_name: '',
  service: 'youtube',
  number_type: 'mobile',
  provider: '',
  base_cost_usd: '1.00',
  tax_basis: 'base' as 'base' | 'subtotal',
  rental_days: 30,
  description: '',
  is_visible: true,
  sales_enabled: false,
  contract_confirmed: false,
  compatibility_confirmed: false,
}
const card = 'rounded-xl border border-border bg-surface p-5'

export function AdminVirtualNumbersPage() {
  const client = useQueryClient()
  const offers = useQuery({ queryKey: ['admin-number-offers'], queryFn: api.offers })
  const orders = useQuery({ queryKey: ['admin-number-orders'], queryFn: api.adminOrders })
  const [id, setId] = useState<string>()
  const [draft, setDraft] = useState(empty)
  const readiness = useQuery({
    queryKey: ['number-payment-readiness'],
    queryFn: api.paymentReadiness,
  })
  const preview = useQuery({
    queryKey: ['number-price-preview', draft.base_cost_usd, draft.tax_basis],
    queryFn: () => api.previewPrice(draft.base_cost_usd, draft.tax_basis),
    enabled: Number(draft.base_cost_usd) >= 1,
  })
  const [stock, setStock] = useState({ offer: '', number: '', provider_reference: '' })
  const refresh = () => {
    void client.invalidateQueries({ queryKey: ['admin-number-offers'] })
    void client.invalidateQueries({ queryKey: ['number-catalog'] })
    void client.invalidateQueries({ queryKey: ['admin-number-orders'] })
  }
  const save = useMutation({
    mutationFn: () => api.saveOffer(draft, id),
    onSuccess: () => {
      refresh()
      setDraft(empty)
      setId(undefined)
    },
  })
  const add = useMutation({
    mutationFn: () => api.addNumber(stock),
    onSuccess: () => {
      refresh()
      setStock({ ...stock, number: '', provider_reference: '' })
    },
  })
  const refund = useMutation({ mutationFn: api.refund, onSuccess: refresh })
  function edit(o: NumberOffer) {
    setId(o.id)
    setDraft({
      name: o.name,
      country_code: o.country_code,
      country_name: o.country_name,
      service: o.service,
      number_type: o.number_type,
      provider: o.provider,
      base_cost_usd: o.base_cost_usd ?? '',
      tax_basis: o.tax_basis ?? 'base',
      rental_days: o.rental_days,
      description: o.description,
      is_visible: !!o.is_visible,
      sales_enabled: !!o.sales_enabled,
      contract_confirmed: !!o.contract_confirmed,
      compatibility_confirmed: !!o.compatibility_confirmed,
    })
  }
  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Virtual raqamlar boshqaruvi</h1>
        <p className="mt-2 text-muted-foreground">
          Davlatlar, tariflar, ajratilgan raqamlar va qaytarish so‘rovlari.
        </p>
      </header>
      <div className={card}>
        <h2 className="font-semibold">Sotuvni ishga tushirish</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          Provayder bilan qayta sotish shartnomasi va xizmatga moslikni tasdiqlang. SMS
          integratsiyasi va to‘lov tizimi sozlangach serverdagi sotuv tugmasi yoqiladi.
          Telegram va WhatsApp uchun faqat mobil raqamlar. Har bir raqam bitta mijozga
          ajratiladi; ishlatilgan raqam qayta sotilmaydi.
        </p>
      </div>
      <section className={card}>
        <h2 className="font-semibold">To‘lov integratsiyalari</h2>
        {readiness.isError && (
          <p role="alert">To‘lov sozlamalari holatini yuklab bo‘lmadi.</p>
        )}
        <div className="mt-3 grid gap-3 md:grid-cols-3">
          {readiness.data?.payment_methods.map((m) => (
            <div key={m.code} className="rounded-lg border border-border p-3">
              <h3 className="font-semibold">{m.label}</h3>
              <p className="mt-1 text-sm">
                {m.available
                  ? `Sozlangan · ${m.mode}`
                  : m.code === 'allpay'
                    ? 'Shartnoma va rasmiy API/HMAC hujjati kerak'
                    : 'Merchant hisobi va server kalitlari kerak'}
              </p>
            </div>
          ))}
        </div>
        <p className="mt-3 text-sm text-muted-foreground">
          Qo‘llanma: docs/PAYMENTS_ONBOARDING_UZ.md. API kalitlari faqat server muhiti
          orqali kiritiladi. Visa kartalari Stripe orqali qabul qilinadi. Ustama 18% —
          to‘lov provayderi komissiyasidan oldingi daromad.
        </p>
      </section>
      {(offers.isError || orders.isError) && (
        <p role="alert">
          Ma’lumotlarni yuklab bo‘lmadi. Admin huquqi va 2FA talab qilinadi.
        </p>
      )}
      {offers.isPending && <p>Yuklanmoqda…</p>}
      <section className={card}>
        <h2 className="mb-4 text-lg font-semibold">
          {id ? 'Taklifni tahrirlash' : 'Yangi taklif'}
        </h2>
        <form
          className="grid gap-4 sm:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault()
            save.mutate()
          }}
        >
          <Input
            required
            label="Taklif nomi"
            maxLength={120}
            value={draft.name}
            onChange={(e) => setDraft({ ...draft, name: e.target.value })}
          />
          <Input
            required
            label="Provayder"
            maxLength={80}
            value={draft.provider}
            onChange={(e) => setDraft({ ...draft, provider: e.target.value })}
          />
          <Input
            required
            label="Davlat kodi (US, GB...)"
            pattern="[A-Z]{2}"
            maxLength={2}
            value={draft.country_code}
            onChange={(e) =>
              setDraft({ ...draft, country_code: e.target.value.toUpperCase() })
            }
          />
          <Input
            required
            label="Davlat nomi"
            maxLength={80}
            value={draft.country_name}
            onChange={(e) => setDraft({ ...draft, country_name: e.target.value })}
          />
          <label>
            Xizmat
            <select
              className="mt-1 block w-full rounded border border-border bg-surface p-2"
              value={draft.service}
              onChange={(e) => setDraft({ ...draft, service: e.target.value })}
            >
              {['youtube', 'telegram', 'whatsapp', 'other'].map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </label>
          <label>
            Raqam turi
            <select
              className="mt-1 block w-full rounded border border-border bg-surface p-2"
              value={draft.number_type}
              onChange={(e) => setDraft({ ...draft, number_type: e.target.value })}
            >
              <option value="mobile">Mobil</option>
              <option value="voip">VoIP</option>
            </select>
          </label>
          <Input
            required
            label="Provayder tannarxi (USD)"
            type="number"
            min={1}
            step="0.01"
            value={draft.base_cost_usd}
            onChange={(e) => setDraft({ ...draft, base_cost_usd: e.target.value })}
          />
          <label>
            Soliq bazasi
            <select
              className="mt-1 block w-full rounded border border-border bg-surface p-2"
              value={draft.tax_basis}
              onChange={(e) =>
                setDraft({ ...draft, tax_basis: e.target.value as 'base' | 'subtotal' })
              }
            >
              <option value="base">Tannarxdan 12% (jami +30%)</option>
              <option value="subtotal">Tannarx + 18% ustamadan 12%</option>
            </select>
          </label>
          <div className="sm:col-span-2">
            <NumberPriceBreakdown price={preview.data} />
            {preview.isError && <p role="alert">Narxni hisoblab bo‘lmadi.</p>}
          </div>
          <Input
            required
            label="Ijara muddati (kun)"
            type="number"
            min={1}
            max={365}
            value={draft.rental_days}
            onChange={(e) => setDraft({ ...draft, rental_days: Number(e.target.value) })}
          />
          <label className="sm:col-span-2">
            Tavsif
            <textarea
              maxLength={2000}
              className="mt-1 block w-full rounded border border-border bg-surface p-2"
              value={draft.description}
              onChange={(e) => setDraft({ ...draft, description: e.target.value })}
            />
          </label>
          {(
            [
              ['is_visible', 'Katalogda ko‘rsatish'],
              ['contract_confirmed', 'Qayta sotish shartnomasi tasdiqlangan'],
              ['compatibility_confirmed', 'Ushbu xizmat uchun moslik tekshirilgan'],
              ['sales_enabled', 'Taklif sotuvini yoqish'],
            ] as const
          ).map(([key, label]) => (
            <label key={key} className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                checked={draft[key]}
                onChange={(e) => setDraft({ ...draft, [key]: e.target.checked })}
              />
              {label}
            </label>
          ))}
          <div className="flex gap-3">
            <Button type="submit" isLoading={save.isPending}>
              Saqlash
            </Button>
            {id && (
              <Button
                variant="outline"
                onClick={() => {
                  setId(undefined)
                  setDraft(empty)
                }}
              >
                Bekor qilish
              </Button>
            )}
          </div>
          {save.isError && <p role="alert">{save.error.message}</p>}
        </form>
      </section>
      <section className="grid gap-3 md:grid-cols-2">
        {offers.data?.map((o) => (
          <article key={o.id} className={card}>
            <h2 className="font-semibold">{o.name}</h2>
            <p className="my-2 text-sm">
              {o.country_name} · {o.service} · ${o.price_usd} / {o.rental_days} kun
            </p>
            <NumberPriceBreakdown price={o.price_breakdown} />
            <p className="mb-3 text-sm text-muted-foreground">
              {o.available_count} ta bo‘sh raqam ·{' '}
              {o.unavailable_reason ? 'Sotuv yopiq' : 'Sotuv ochiq'}
            </p>
            <Button variant="outline" onClick={() => edit(o)}>
              Tahrirlash
            </Button>
          </article>
        ))}
      </section>
      <section className={card}>
        <h2 className="mb-4 text-lg font-semibold">
          Provayderdan olingan raqamni qo‘shish
        </h2>
        <form
          className="grid gap-4 sm:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault()
            add.mutate()
          }}
        >
          <label>
            Taklif
            <select
              required
              className="mt-1 block w-full rounded border border-border bg-surface p-2"
              value={stock.offer}
              onChange={(e) => setStock({ ...stock, offer: e.target.value })}
            >
              <option value="">Tanlang</option>
              {offers.data?.map((o) => (
                <option key={o.id} value={o.id}>
                  {o.name}
                </option>
              ))}
            </select>
          </label>
          <Input
            required
            label="Telefon raqami (+...)"
            pattern="\+[1-9][0-9]{6,14}"
            value={stock.number}
            onChange={(e) => setStock({ ...stock, number: e.target.value })}
          />
          <Input
            required
            maxLength={160}
            label="Provayderdagi yagona raqam IDsi"
            value={stock.provider_reference}
            onChange={(e) => setStock({ ...stock, provider_reference: e.target.value })}
          />
          <Button className="self-end" type="submit" isLoading={add.isPending}>
            Raqam qo‘shish
          </Button>
          {add.isError && <p role="alert">{add.error.message}</p>}
          {add.isSuccess && <p role="status">Raqam qo‘shildi.</p>}
        </form>
      </section>
      <section className="space-y-3">
        <h2 className="text-xl font-semibold">So‘nggi 100 buyurtma</h2>
        {orders.data?.length === 0 && <p>Hali buyurtma yo‘q.</p>}
        {refund.isError && <p role="alert">{refund.error.message}</p>}
        {orders.data?.map((o) => (
          <article className={card} key={o.id}>
            <h3 className="font-semibold">
              {o.offer_name} · ${o.price_usd}
            </h3>
            <p className="mt-2 break-all text-sm text-muted-foreground">
              Buyurtma: {o.id}
              <br />
              Mijoz: {o.user_id}
              <br />
              {numberStatus[o.status] ?? o.status}
            </p>
            {o.refund_reason && <p className="my-3">Sabab: {o.refund_reason}</p>}
            {o.status === 'refund_requested' && (
              <Button
                variant="destructive"
                isLoading={refund.isPending}
                onClick={() => {
                  if (
                    window.confirm(
                      `$${o.price_usd} to‘liq qaytarilsinmi? Raqam xizmati to‘xtatiladi.`,
                    )
                  )
                    refund.mutate(o.id)
                }}
              >
                Pulni to‘lov tizimi orqali qaytarish
              </Button>
            )}
          </article>
        ))}
      </section>
    </div>
  )
}

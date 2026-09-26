import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FileText, Globe2 } from 'lucide-react'
import {
  adminWebServicesApi as api,
  type ExecutorProfile,
  type ServiceOrder,
  type ServicePackage,
} from '@/api/webServices'
import { Button } from '@/components/ui/Button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'

const statusLabel: Record<string, string> = {
  pending_payment: 'To‘lov kutilmoqda',
  paid: 'To‘langan',
  in_progress: 'Ishlanmoqda',
  delivered: 'Topshirildi',
  canceled: 'Bekor qilingan',
  refund_pending: 'Qaytarilmoqda',
  refunded: 'Qaytarilgan',
}
const action: Record<string, string> = {
  canceled: 'Bekor qilish',
  in_progress: 'Ishni boshlash',
  delivered: 'Topshirildi',
}
const next: Record<string, string[]> = {
  pending_payment: ['canceled'],
  paid: ['in_progress'],
  in_progress: ['delivered'],
  delivered: ['in_progress'],
}
const packageName: Record<string, string> = {
  starter: 'Start',
  business: 'Business',
  pro: 'Pro',
  enterprise: 'Enterprise',
}
const reasons: Record<string, string> = {
  sales_paused: 'Sotuv o‘chirilgan.',
  executor_details_required: 'Ijrochi rekvizitlari to‘liq emas.',
  payment_account_required: 'Asosiy Payoneer Checkout hisobi tanlanmagan.',
}

const executorFields: [keyof ExecutorProfile, string, boolean?][] = [
  ['legal_name', 'Yuridik nomi (masalan «Creator AI» MChJ)', true],
  ['director_name', 'Rahbar F.I.Sh.', true],
  ['acting_basis', 'Vakolat asosi (uz)'],
  ['acting_basis_en', 'Vakolat asosi (en)'],
  ['address', 'Yuridik manzil', true],
  ['city', 'Shahar (uz)'],
  ['city_en', 'Shahar (en)'],
  ['tin', 'STIR', true],
  ['bank_name', 'Bank'],
  ['bank_account', 'Hisob raqami'],
  ['bank_code', 'MFO'],
  ['swift', 'SWIFT'],
  ['phone', 'Telefon', true],
  ['email', 'E-mail', true],
  ['vat_note', 'QQS izohi (rezident shartnomasida narxdan keyin)'],
]

function Executor() {
  const cache = useQueryClient()
  const profile = useQuery({ queryKey: ['ws-executor'], queryFn: api.executor })
  const [draft, setDraft] = useState<Partial<ExecutorProfile>>({})
  const value = { ...profile.data, ...draft }
  const save = useMutation({
    mutationFn: (patch: Partial<ExecutorProfile>) => api.saveExecutor(patch),
    onSuccess: (data) => {
      setDraft({})
      cache.setQueryData(['ws-executor'], data)
    },
    onSettled: () => cache.invalidateQueries({ queryKey: ['ws-executor'] }),
  })
  return (
    <Card>
      <CardHeader>
        <CardTitle>Ijrochi rekvizitlari</CardTitle>
        <p className="text-sm text-muted-foreground">
          Har bir shartnomaga shu ma’lumotlar kiritiladi. Buyurtma paytidagi nusxa
          shartnomada o‘zgarmas saqlanadi.
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        <form
          className="grid gap-4 sm:grid-cols-2"
          onSubmit={(e) => {
            e.preventDefault()
            save.mutate(draft)
          }}
        >
          {executorFields.map(([key, label, required]) => (
            <Input
              key={key}
              label={label}
              required={required}
              value={String(value[key] ?? '')}
              onChange={(e) => setDraft((d) => ({ ...d, [key]: e.target.value }))}
            />
          ))}
          <div className="flex items-end">
            <Button
              type="submit"
              isLoading={save.isPending && !('sales_enabled' in (save.variables ?? {}))}
            >
              Rekvizitlarni saqlash
            </Button>
          </div>
        </form>
        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-border p-4">
          <p className="text-sm">
            Holat:{' '}
            <strong>
              {profile.data?.sales_ready ? 'buyurtmalar qabul qilinmoqda' : 'yopiq'}
            </strong>
            {profile.data?.reason &&
              ` — ${reasons[profile.data.reason] ?? profile.data.reason}`}
          </p>
          <Button
            variant="outline"
            onClick={() => save.mutate({ sales_enabled: !profile.data?.sales_enabled })}
          >
            {profile.data?.sales_enabled ? 'Sotuvni to‘xtatish' : 'Sotuvni ochish'}
          </Button>
        </div>
        {save.isError && (
          <p role="alert" className="text-sm text-destructive-600">
            {save.error.message}
          </p>
        )}
      </CardContent>
    </Card>
  )
}

const packageFields: [keyof ServicePackage, string][] = [
  ['price_usd', 'Narx, USD'],
  ['delivery_days', 'Muddat (ish kuni)'],
  ['revision_rounds', 'Tuzatishlar'],
  ['support_months', 'Qo‘llab-quvvatlash (oy)'],
  ['page_limit', 'Sahifalar (0 = TT bo‘yicha)'],
  ['languages', 'Tillar'],
]

function PackageRow({ pkg }: { pkg: ServicePackage }) {
  const cache = useQueryClient()
  const [draft, setDraft] = useState<Partial<ServicePackage>>({})
  const save = useMutation({
    mutationFn: () => api.savePackage(pkg.id, draft),
    onSuccess: () => {
      setDraft({})
      void cache.invalidateQueries({ queryKey: ['ws-packages'] })
    },
  })
  const value = { ...pkg, ...draft }
  return (
    <form
      className="grid items-end gap-3 border-b border-border py-4 sm:grid-cols-8"
      onSubmit={(e) => {
        e.preventDefault()
        save.mutate()
      }}
    >
      <div>
        <p className="font-semibold">{packageName[pkg.code] ?? pkg.code}</p>
        <label className="mt-1 flex items-center gap-2 text-xs">
          <input
            type="checkbox"
            checked={!!value.is_active}
            onChange={(e) => setDraft((d) => ({ ...d, is_active: e.target.checked }))}
          />
          Faol
        </label>
      </div>
      {packageFields.map(([key, label]) => (
        <Input
          key={key}
          label={label}
          type="number"
          min={key === 'page_limit' ? 0 : 1}
          step={key === 'price_usd' ? '0.01' : '1'}
          value={String(value[key])}
          onChange={(e) => setDraft((d) => ({ ...d, [key]: e.target.value }))}
        />
      ))}
      <Button
        type="submit"
        variant="outline"
        disabled={!Object.keys(draft).length}
        isLoading={save.isPending}
      >
        Saqlash
      </Button>
      {save.isError && (
        <p role="alert" className="text-sm text-destructive-600 sm:col-span-8">
          {save.error.message}
        </p>
      )}
    </form>
  )
}

function OrderRow({ order }: { order: ServiceOrder }) {
  const cache = useQueryClient()
  const refresh = () => cache.invalidateQueries({ queryKey: ['ws-orders'] })
  const status = useMutation({
    mutationFn: (value: string) => api.setStatus(order.id, value),
    onSuccess: refresh,
  })
  const refund = useMutation({
    mutationFn: () => api.refund(order.id),
    onSuccess: refresh,
  })
  const confirm = useMutation({
    mutationFn: () => api.confirm(order.id),
    onSuccess: refresh,
  })
  const error = status.error ?? refund.error ?? confirm.error
  return (
    <tr className="align-top">
      <td className="py-3">
        <p className="font-medium">{order.number}</p>
        <p className="text-xs text-muted-foreground">
          {new Date(order.created_at).toLocaleString()}
        </p>
      </td>
      <td>
        <p>{order.user_email}</p>
        <p className="text-xs text-muted-foreground">
          {order.contract_type === 'resident' ? 'Rezident' : 'Chet el fuqarosi'}
        </p>
      </td>
      <td>
        <p>
          {packageName[order.package]} · ${order.price_usd}
        </p>
        <p
          className="max-w-[14rem] truncate text-xs text-muted-foreground"
          title={order.project_name}
        >
          {order.project_name}
        </p>
      </td>
      <td>
        <p>{statusLabel[order.status] ?? order.status}</p>
        <p className="text-xs text-muted-foreground">{order.account_label}</p>
        {error && (
          <p role="alert" className="text-xs text-destructive-600">
            {error.message}
          </p>
        )}
      </td>
      <td className="space-x-1 space-y-1 text-right">
        <Link
          to={`/admin/web-services/orders/${order.id}/contract`}
          className="inline-flex h-8 items-center gap-1 rounded-md border border-border px-2 text-xs hover:bg-muted"
        >
          <FileText size={13} /> Shartnoma
        </Link>
        {(next[order.status] ?? []).map((value) => (
          <Button
            key={value}
            size="sm"
            variant="outline"
            isLoading={status.isPending && status.variables === value}
            onClick={() => {
              if (
                value !== 'canceled' ||
                window.confirm(`${order.number} bekor qilinsinmi?`)
              )
                status.mutate(value)
            }}
          >
            {order.status === 'delivered' ? 'Qayta ishlashga qaytarish' : action[value]}
          </Button>
        ))}
        {order.status === 'pending_payment' && (
          <Button
            size="sm"
            variant="outline"
            isLoading={confirm.isPending}
            onClick={() => confirm.mutate()}
          >
            To‘lovni tekshirish
          </Button>
        )}
        {['paid', 'in_progress', 'delivered', 'refund_pending'].includes(
          order.status,
        ) && (
          <Button
            size="sm"
            variant="outline"
            isLoading={refund.isPending}
            onClick={() => {
              if (
                window.confirm(
                  `${order.number}: ${order.price_usd} USD Payoneer orqali qaytarilsinmi?`,
                )
              )
                refund.mutate()
            }}
          >
            Pulni qaytarish
          </Button>
        )}
      </td>
    </tr>
  )
}

export function AdminWebServicesPage() {
  const packages = useQuery({ queryKey: ['ws-packages'], queryFn: api.packages })
  const orders = useQuery({
    queryKey: ['ws-orders'],
    queryFn: api.orders,
    refetchInterval: 30000,
  })
  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <header className="flex items-center gap-3">
        <Globe2 className="text-primary-600" />
        <div>
          <h1 className="text-2xl font-semibold">Sayt yaratish xizmatlari</h1>
          <p className="text-sm text-muted-foreground">
            Paketlar, shartnoma rekvizitlari va buyurtmalar. To‘lovlar Payoneer orqali
            qabul qilinadi.
          </p>
        </div>
      </header>

      <Card>
        <CardHeader>
          <CardTitle>Buyurtmalar</CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          {orders.data?.length === 0 && (
            <p className="text-sm text-muted-foreground">Hali buyurtma yo‘q.</p>
          )}
          {!!orders.data?.length && (
            <table className="w-full text-left text-sm">
              <thead className="text-xs text-muted-foreground">
                <tr>
                  <th className="py-2">Raqam</th>
                  <th>Mijoz</th>
                  <th>Paket</th>
                  <th>Holat</th>
                  <th />
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {orders.data.map((o) => (
                  <OrderRow key={o.id} order={o} />
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Paketlar</CardTitle>
          <p className="text-sm text-muted-foreground">
            O‘zgarishlar faqat yangi shartnomalarga ta’sir qiladi. Paket tarkibi matni
            shartnoma shablonida.
          </p>
        </CardHeader>
        <CardContent>
          {packages.data?.map((p) => (
            <PackageRow key={p.id} pkg={p} />
          ))}
        </CardContent>
      </Card>

      <Executor />
    </div>
  )
}

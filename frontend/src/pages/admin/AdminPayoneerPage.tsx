import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Copy, RefreshCw, Send, Wallet, XCircle } from 'lucide-react'
import {
  payoneerApi as api,
  type PayoneerAccount,
  type PayoneerAccountInput,
} from '@/api/payoneer'
import { Button } from '@/components/ui/Button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'

const blank: PayoneerAccountInput = {
  label: '',
  environment: 'sandbox',
  is_active: true,
  checkout_enabled: true,
  is_default_checkout: false,
  merchant_code: '',
  division: '',
  payment_token: '',
  payouts_enabled: false,
  is_default_payouts: false,
  program_id: '',
  client_id: '',
  client_secret: '',
}

const payoutStatus: Record<string, string> = {
  submitting: 'Yuborilmoqda',
  pending: 'Kutilmoqda',
  transferred: 'O‘tkazildi',
  failed: 'Xato',
  canceled: 'Bekor qilindi',
}
const payeeStatus: Record<string, string> = {
  invited: 'Taklif qilingan',
  active: 'Faol',
  inactive: 'Nofaol',
}

function Toggle({
  label,
  checked,
  onChange,
}: {
  label: string
  checked: boolean
  onChange: (value: boolean) => void
}) {
  return (
    <label className="flex items-center gap-2 text-sm">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      {label}
    </label>
  )
}

function copy(text: string) {
  void navigator.clipboard?.writeText(text)
}

function AccountForm({
  initial,
  id,
  onDone,
}: {
  initial: PayoneerAccountInput
  id?: string
  onDone: () => void
}) {
  const cache = useQueryClient()
  const [draft, setDraft] = useState(initial)
  const set = <K extends keyof PayoneerAccountInput>(
    key: K,
    value: PayoneerAccountInput[K],
  ) => setDraft((d) => ({ ...d, [key]: value }))
  const save = useMutation({
    mutationFn: () => api.saveAccount(draft, id),
    onSuccess: async () => {
      await cache.invalidateQueries({ queryKey: ['payoneer-accounts'] })
      onDone()
    },
  })
  const secretHint = id ? 'Saqlangan. O‘zgartirish uchungina kiriting.' : undefined
  return (
    <form
      className="space-y-5"
      onSubmit={(e) => {
        e.preventDefault()
        save.mutate()
      }}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Input
          label="Hisob nomi"
          required
          value={draft.label}
          onChange={(e) => set('label', e.target.value)}
          placeholder="Masalan: Asosiy MChJ — live"
        />
        <Select
          label="Muhit"
          value={draft.environment}
          onChange={(e) => set('environment', e.target.value as 'sandbox' | 'live')}
          options={[
            { value: 'sandbox', label: 'Sandbox (sinov)' },
            { value: 'live', label: 'Live (haqiqiy to‘lovlar)' },
          ]}
        />
      </div>
      <Toggle
        label="Hisob faol"
        checked={!!draft.is_active}
        onChange={(v) => set('is_active', v)}
      />

      <fieldset className="space-y-3 rounded-lg border border-border p-4">
        <legend className="px-1 text-sm font-semibold">
          Payoneer Checkout — to‘lov qabul qilish
        </legend>
        <div className="flex flex-wrap gap-5">
          <Toggle
            label="Yoqilgan"
            checked={!!draft.checkout_enabled}
            onChange={(v) => set('checkout_enabled', v)}
          />
          <Toggle
            label="Asosiy hisob (yangi buyurtmalar shu hisobga)"
            checked={!!draft.is_default_checkout}
            onChange={(v) => set('is_default_checkout', v)}
          />
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          <Input
            label="Merchant code"
            value={draft.merchant_code}
            onChange={(e) => set('merchant_code', e.target.value)}
          />
          <Input
            label="Division (store code)"
            value={draft.division}
            onChange={(e) => set('division', e.target.value)}
          />
          <Input
            label="Payment API token"
            type="password"
            autoComplete="new-password"
            hint={secretHint}
            value={draft.payment_token}
            onChange={(e) => set('payment_token', e.target.value)}
          />
        </div>
      </fieldset>

      <fieldset className="space-y-3 rounded-lg border border-border p-4">
        <legend className="px-1 text-sm font-semibold">
          Mass Payouts — to‘lov chiqarish
        </legend>
        <div className="flex flex-wrap gap-5">
          <Toggle
            label="Yoqilgan"
            checked={!!draft.payouts_enabled}
            onChange={(v) => set('payouts_enabled', v)}
          />
          <Toggle
            label="Asosiy payout hisobi"
            checked={!!draft.is_default_payouts}
            onChange={(v) => set('is_default_payouts', v)}
          />
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          <Input
            label="Program ID"
            value={draft.program_id}
            onChange={(e) => set('program_id', e.target.value)}
          />
          <Input
            label="Client ID"
            value={draft.client_id}
            onChange={(e) => set('client_id', e.target.value)}
          />
          <Input
            label="Client secret"
            type="password"
            autoComplete="new-password"
            hint={secretHint}
            value={draft.client_secret}
            onChange={(e) => set('client_secret', e.target.value)}
          />
        </div>
      </fieldset>

      <div className="flex flex-wrap items-center gap-3">
        <Button type="submit" isLoading={save.isPending}>
          Saqlash
        </Button>
        <Button type="button" variant="outline" onClick={onDone}>
          Bekor qilish
        </Button>
        {save.isError && (
          <p role="alert" className="text-sm text-destructive-600">
            {save.error.message}
          </p>
        )}
      </div>
    </form>
  )
}

function AccountRow({
  account,
  onEdit,
}: {
  account: PayoneerAccount
  onEdit: () => void
}) {
  const cache = useQueryClient()
  const refresh = () => cache.invalidateQueries({ queryKey: ['payoneer-accounts'] })
  const check = useMutation({
    mutationFn: () => api.checkAccount(account.id),
    onSuccess: refresh,
  })
  const remove = useMutation({
    mutationFn: () => api.removeAccount(account.id),
    onSuccess: refresh,
  })
  return (
    <li className="space-y-2 py-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-semibold">
            {account.label}{' '}
            <span className="rounded bg-muted px-1.5 py-0.5 text-xs font-normal">
              {account.environment === 'live' ? 'LIVE' : 'SANDBOX'}
            </span>
            {!account.is_active && (
              <span className="ml-2 text-xs text-muted-foreground">nofaol</span>
            )}
          </p>
          <p className="text-sm text-muted-foreground">
            Checkout: {account.checkout_ready ? 'tayyor' : 'sozlanmagan'}
            {account.is_default_checkout && ' · asosiy'} · Payouts:{' '}
            {account.payouts_ready ? 'tayyor' : 'sozlanmagan'}
            {account.is_default_payouts && ' · asosiy'}
          </p>
          {account.last_checked_at && (
            <p className="mt-1 flex items-center gap-1 text-xs">
              {account.last_check_ok ? (
                <CheckCircle2 size={14} className="text-emerald-600" />
              ) : (
                <XCircle size={14} className="text-destructive-600" />
              )}
              {account.last_check_detail} ·{' '}
              {new Date(account.last_checked_at).toLocaleString()}
            </p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            size="sm"
            variant="outline"
            isLoading={check.isPending}
            onClick={() => check.mutate()}
          >
            Ulanishni tekshirish
          </Button>
          <Button size="sm" variant="outline" onClick={onEdit}>
            Tahrirlash
          </Button>
          <Button
            size="sm"
            variant="outline"
            isLoading={remove.isPending}
            onClick={() => {
              if (
                window.confirm(
                  `«${account.label}» hisobini o‘chirasizmi? Buyurtmalari bo‘lsa, faqat nofaol qilinadi.`,
                )
              )
                remove.mutate()
            }}
          >
            O‘chirish
          </Button>
        </div>
      </div>
      {account.checkout_enabled && (
        <p className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          Bildirishnoma URL (Payoneer kabinetiga shart emas — har so‘rovda yuboriladi):
          <code className="break-all rounded bg-muted px-1.5 py-0.5">
            {account.notification_url}
          </code>
          <button
            type="button"
            onClick={() => copy(account.notification_url)}
            aria-label="Nusxalash"
          >
            <Copy size={14} />
          </button>
        </p>
      )}
    </li>
  )
}

function Payees({ accounts }: { accounts: PayoneerAccount[] }) {
  const cache = useQueryClient()
  const payees = useQuery({ queryKey: ['payoneer-payees'], queryFn: api.payees })
  const ready = accounts.filter((a) => a.payouts_ready)
  const [draft, setDraft] = useState({ account: '', display_name: '', email: '' })
  const [link, setLink] = useState<{ id: string; url: string }>()
  const refresh = () => cache.invalidateQueries({ queryKey: ['payoneer-payees'] })
  const add = useMutation({
    mutationFn: () =>
      api.addPayee({ ...draft, account: draft.account || ready[0]?.id || '' }),
    onSuccess: () => {
      setDraft({ account: '', display_name: '', email: '' })
      void refresh()
    },
  })
  const invite = useMutation({
    mutationFn: api.invitePayee,
    onSuccess: (data, id) => setLink({ id, url: data.registration_link }),
  })
  const status = useMutation({ mutationFn: api.refreshPayee, onSuccess: refresh })
  return (
    <Card>
      <CardHeader>
        <CardTitle>To‘lov oluvchilar (payee)</CardTitle>
        <p className="text-sm text-muted-foreground">
          Hamkor yoki ijrochi qo‘shing, so‘ng unga Payoneer ro‘yxatdan o‘tish havolasini
          yuboring. Holati «Faol» bo‘lgach, unga to‘lov chiqarish mumkin.
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        {ready.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Avval Mass Payouts sozlangan hisob qo‘shing.
          </p>
        ) : (
          <form
            className="grid items-end gap-3 sm:grid-cols-4"
            onSubmit={(e) => {
              e.preventDefault()
              add.mutate()
            }}
          >
            <Select
              label="Hisob"
              value={draft.account || ready[0].id}
              onChange={(e) => setDraft((d) => ({ ...d, account: e.target.value }))}
              options={ready.map((a) => ({ value: a.id, label: a.label }))}
            />
            <Input
              label="Ism yoki kompaniya"
              required
              value={draft.display_name}
              onChange={(e) => setDraft((d) => ({ ...d, display_name: e.target.value }))}
            />
            <Input
              label="E-mail"
              type="email"
              value={draft.email}
              onChange={(e) => setDraft((d) => ({ ...d, email: e.target.value }))}
            />
            <Button type="submit" isLoading={add.isPending}>
              Qo‘shish
            </Button>
          </form>
        )}
        {(add.isError || invite.isError || status.isError) && (
          <p role="alert" className="text-sm text-destructive-600">
            {(add.error ?? invite.error ?? status.error)?.message}
          </p>
        )}
        <ul className="divide-y divide-border">
          {payees.data?.map((p) => (
            <li
              key={p.id}
              className="flex flex-wrap items-center justify-between gap-3 py-3"
            >
              <div>
                <p className="font-medium">{p.display_name}</p>
                <p className="text-xs text-muted-foreground">
                  {p.payee_id} · {p.account_label} · {payeeStatus[p.status]}
                  {p.provider_status && ` (${p.provider_status})`}
                </p>
                {link?.id === p.id && (
                  <p className="mt-1 flex items-center gap-2 text-xs">
                    <code className="break-all rounded bg-muted px-1.5 py-0.5">
                      {link.url}
                    </code>
                    <button
                      type="button"
                      onClick={() => copy(link.url)}
                      aria-label="Nusxalash"
                    >
                      <Copy size={14} />
                    </button>
                  </p>
                )}
              </div>
              <div className="flex gap-2">
                <Button size="sm" variant="outline" onClick={() => invite.mutate(p.id)}>
                  Ro‘yxatdan o‘tish havolasi
                </Button>
                <Button size="sm" variant="outline" onClick={() => status.mutate(p.id)}>
                  <RefreshCw size={14} /> Holat
                </Button>
              </div>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  )
}

function Payouts() {
  const cache = useQueryClient()
  const payees = useQuery({ queryKey: ['payoneer-payees'], queryFn: api.payees })
  const payouts = useQuery({ queryKey: ['payoneer-payouts'], queryFn: api.payouts })
  const active = payees.data?.filter((p) => p.status === 'active') ?? []
  const [draft, setDraft] = useState({ payee: '', amount: '', description: '' })
  const refresh = () => cache.invalidateQueries({ queryKey: ['payoneer-payouts'] })
  const create = useMutation({
    mutationFn: () =>
      api.createPayout({ ...draft, payee: draft.payee || active[0]?.id || '' }),
    onSuccess: () => {
      setDraft({ payee: '', amount: '', description: '' })
      void refresh()
    },
    onError: refresh,
  })
  const submit = useMutation({ mutationFn: api.submitPayout, onSuccess: refresh })
  const status = useMutation({ mutationFn: api.refreshPayout, onSuccess: refresh })
  const payeeName = active.find(
    (p) => p.id === (draft.payee || active[0]?.id),
  )?.display_name
  return (
    <Card>
      <CardHeader>
        <CardTitle>To‘lov chiqarish (payout)</CardTitle>
        <p className="text-sm text-muted-foreground">
          Pul darhol Payoneer orqali yuboriladi. Har bir to‘lovning noyob ID si bor,
          shuning uchun qayta yuborish ikki marta to‘lamaydi.
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        {active.length === 0 ? (
          <p className="text-sm text-muted-foreground">Faol to‘lov oluvchi yo‘q.</p>
        ) : (
          <form
            className="grid items-end gap-3 sm:grid-cols-4"
            onSubmit={(e) => {
              e.preventDefault()
              if (window.confirm(`${payeeName} ga ${draft.amount} USD yuborilsinmi?`))
                create.mutate()
            }}
          >
            <Select
              label="Kimga"
              value={draft.payee || active[0].id}
              onChange={(e) => setDraft((d) => ({ ...d, payee: e.target.value }))}
              options={active.map((p) => ({ value: p.id, label: p.display_name }))}
            />
            <Input
              label="Summa, USD"
              type="number"
              min="1"
              step="0.01"
              required
              value={draft.amount}
              onChange={(e) => setDraft((d) => ({ ...d, amount: e.target.value }))}
            />
            <Input
              label="Izoh"
              required
              minLength={3}
              maxLength={200}
              value={draft.description}
              onChange={(e) => setDraft((d) => ({ ...d, description: e.target.value }))}
              placeholder="Masalan: WS-2026-00012 dizayn"
            />
            <Button type="submit" isLoading={create.isPending}>
              <Send size={14} /> Yuborish
            </Button>
          </form>
        )}
        {(create.isError || submit.isError || status.isError) && (
          <p role="alert" className="text-sm text-destructive-600">
            {(create.error ?? submit.error ?? status.error)?.message}
          </p>
        )}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-muted-foreground">
              <tr>
                <th className="py-2">Sana</th>
                <th>Kimga</th>
                <th>Summa</th>
                <th>Izoh</th>
                <th>Holat</th>
                <th />
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {payouts.data?.map((p) => (
                <tr key={p.id}>
                  <td className="py-2">{new Date(p.created_at).toLocaleDateString()}</td>
                  <td>{p.payee_name}</td>
                  <td>
                    {p.amount} {p.currency}
                  </td>
                  <td className="max-w-[16rem] truncate" title={p.description}>
                    {p.description}
                  </td>
                  <td title={p.reason}>
                    {payoutStatus[p.status]}
                    {p.provider_status && ` (${p.provider_status})`}
                  </td>
                  <td className="whitespace-nowrap text-right">
                    {p.status === 'submitting' && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => submit.mutate(p.id)}
                      >
                        Qayta yuborish
                      </Button>
                    )}{' '}
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => status.mutate(p.id)}
                    >
                      <RefreshCw size={14} />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  )
}

export function AdminPayoneerPage() {
  const accounts = useQuery({ queryKey: ['payoneer-accounts'], queryFn: api.accounts })
  const [editing, setEditing] = useState<{ id?: string; initial: PayoneerAccountInput }>()
  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <header className="flex items-center gap-3">
        <Wallet className="text-primary-600" />
        <div>
          <h1 className="text-2xl font-semibold">Payoneer</h1>
          <p className="text-sm text-muted-foreground">
            Bir nechta Payoneer hisobini ulang: to‘lov qabul qilish (Checkout) va to‘lov
            chiqarish (Mass Payouts). Kalitlar shifrlangan holda saqlanadi va qayta
            ko‘rsatilmaydi.
          </p>
        </div>
      </header>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between gap-3">
          <CardTitle>Hisoblar</CardTitle>
          {!editing && (
            <Button onClick={() => setEditing({ initial: blank })}>Hisob qo‘shish</Button>
          )}
        </CardHeader>
        <CardContent>
          {editing && (
            <div className="mb-6 rounded-lg bg-muted/40 p-4">
              <AccountForm
                key={editing.id ?? 'new'}
                id={editing.id}
                initial={editing.initial}
                onDone={() => setEditing(undefined)}
              />
            </div>
          )}
          {accounts.data?.length === 0 && !editing && (
            <p className="text-sm text-muted-foreground">Hali hisob qo‘shilmagan.</p>
          )}
          <ul className="divide-y divide-border">
            {accounts.data?.map((a) => (
              <AccountRow
                key={a.id}
                account={a}
                onEdit={() =>
                  setEditing({
                    id: a.id,
                    initial: { ...a, payment_token: '', client_secret: '' },
                  })
                }
              />
            ))}
          </ul>
        </CardContent>
      </Card>

      <Payees accounts={accounts.data ?? []} />
      <Payouts />
    </div>
  )
}

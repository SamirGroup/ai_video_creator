import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { assistantApi, type Policy } from '@/api/assistant'
import { adminNavItems } from '@/components/layout/navConfig'
import { useAuth } from '@/hooks/useAuth'
import { ErrorState } from '@/components/common/StateViews'
import { Button } from '@/components/ui/Button'
function PolicyForm({ policy }: { policy: Policy }) {
  const [form, setForm] = useState(policy)
  const cache = useQueryClient()
  const save = useMutation({
    mutationFn: () => assistantApi.policy(form),
    onSuccess: () => cache.invalidateQueries({ queryKey: ['operations'] }),
  })
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        save.mutate()
      }}
      className="space-y-4"
    >
      <h2 className="font-semibold">AI yordamchi boshqaruvi</h2>
      <label className="flex items-center gap-3 text-sm">
        <input
          type="checkbox"
          checked={form.enabled}
          onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
        />
        Mijozlar uchun yordamchini yoqish
      </label>
      <label className="block text-xs text-muted-foreground">
        Har bir mijoz uchun kunlik xabar limiti
        <input
          type="number"
          min={1}
          max={100}
          required
          className="mt-2 w-full rounded-lg border border-border bg-background p-2.5 text-foreground"
          value={form.daily_message_limit}
          onChange={(e) =>
            setForm({ ...form, daily_message_limit: Number(e.target.value) })
          }
        />
      </label>
      <label className="block text-xs text-muted-foreground">
        Yordamchiga xizmat ko‘rsatish ko‘rsatmalari
        <textarea
          maxLength={2000}
          className="mt-2 min-h-24 w-full rounded-lg border border-border bg-background p-3 text-foreground"
          value={form.guidance}
          onChange={(e) => setForm({ ...form, guidance: e.target.value })}
          placeholder="Mijozlarga aniq, qisqa va tushunarli maslahat bering."
        />
      </label>
      <Button type="submit" disabled={save.isPending}>
        {save.isPending ? 'Saqlanmoqda…' : 'Sozlamalarni saqlash'}
      </Button>
      {save.isSuccess && (
        <p role="status" className="text-xs text-emerald-500">
          Saqlandi
        </p>
      )}
      {save.isError && (
        <p role="alert" className="text-xs text-red-400">
          {save.error.message}
        </p>
      )}
    </form>
  )
}
export function AdminDashboardPage() {
  const { t } = useTranslation()
  const { hasAnyRole } = useAuth()
  const query = useQuery({
    queryKey: ['operations'],
    queryFn: assistantApi.overview,
    refetchInterval: 30000,
  })
  if (query.isError) return <ErrorState onRetry={() => query.refetch()} />
  const data = query.data
  const total = data?.jobs.reduce((sum, j) => sum + j.count, 0) || 0
  const missing = data?.integrations.filter((p) => p.active && !p.configured).length || 0
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="workspace-eyebrow">ADMIN / OPERATIONS</p>
          <h1 className="mt-1 text-2xl font-semibold">Boshqaruv paneli</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Mijozlar, AI xizmatlari va kontent jarayoni — yagona markazda.
          </p>
        </div>
        <Button
          variant="secondary"
          onClick={() => query.refetch()}
          disabled={query.isFetching}
        >
          ↻ Yangilash
        </Button>
      </div>
      {missing > 0 && (
        <div
          role="status"
          className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-500/20 bg-amber-500/10 p-4 text-sm text-amber-500"
        >
          <span>
            {missing} ta faol AI xizmatida kalit yetishmayapti. Haqiqiy generatsiya
            ulanishdan keyin ishlaydi.
          </span>
          <Link to="/admin/config" className="font-semibold underline">
            Integratsiyalarni sozlash ↗
          </Link>
        </div>
      )}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[
          ['Faol foydalanuvchilar', data?.users],
          ['Ulangan kanallar', data?.connected_channels],
          ['Video topshiriqlari', data ? total : undefined],
          [
            'AI sarfi · 30 kun',
            data ? '$' + Number(data.ai_cost_30d).toFixed(2) : undefined,
          ],
        ].map(([label, value]) => (
          <div className="workspace-card" key={label}>
            <p className="workspace-eyebrow">{label}</p>
            <p className="mt-3 text-2xl font-semibold">{value ?? '—'}</p>
            <div className="mt-4 h-0.5 w-12 rounded bg-orange-400/60" />
          </div>
        ))}
      </div>
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_330px]">
        <section className="workspace-card !p-0">
          <div className="flex items-center justify-between border-b border-border p-5">
            <h2 className="font-semibold">AI integratsiyalari</h2>
            <span className="text-xs text-muted-foreground">Haqiqiy konfiguratsiya</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-muted/50 text-xs text-muted-foreground">
                <tr>
                  {['Xizmat', 'Provayder / model', 'Holat'].map((x) => (
                    <th className="px-5 py-3 font-medium" key={x}>
                      {x}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data?.integrations.map((p, i) => (
                  <tr className="border-t border-border" key={i}>
                    <td className="px-5 py-4">{p.service}</td>
                    <td className="px-5 py-4">
                      <p>{p.provider}</p>
                      <p
                        className="mt-1 max-w-72 truncate text-xs text-muted-foreground"
                        title={p.model}
                      >
                        {p.model}
                      </p>
                    </td>
                    <td className="px-5 py-4">
                      <span
                        className={`whitespace-nowrap rounded-md px-2 py-1 text-xs ${!p.active ? 'bg-muted text-muted-foreground' : p.configured ? 'bg-emerald-500/10 text-emerald-500' : 'bg-amber-500/10 text-amber-500'}`}
                      >
                        {!p.active
                          ? 'O‘chirilgan'
                          : p.configured
                            ? 'Sozlangan'
                            : 'Kalit kerak'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data?.integrations.length === 0 && (
            <p className="p-5 text-muted-foreground">Provayderlar hali qo‘shilmagan.</p>
          )}
          <p className="border-t border-border p-4 text-xs text-muted-foreground">
            “Sozlangan” kalit mavjudligini bildiradi. Xizmat ishlashi haqiqiy so‘rov bilan
            tekshiriladi.
          </p>
        </section>
        <section className="workspace-card">
          <h2 className="font-semibold">Kontent jarayoni</h2>
          <p className="mt-1 text-xs text-muted-foreground">Barcha mijozlar bo‘yicha</p>
          <div className="mt-5 space-y-4">
            {data?.jobs.map((j) => (
              <div key={j.status}>
                <div className="mb-2 flex justify-between text-xs">
                  <span>{j.status}</span>
                  <span>{j.count}</span>
                </div>
                <div className="h-1.5 overflow-hidden rounded bg-muted">
                  <div
                    className="h-full rounded bg-orange-400"
                    style={{ width: `${total ? (j.count / total) * 100 : 0}%` }}
                  />
                </div>
              </div>
            ))}
            {data && total === 0 && (
              <p className="text-sm text-muted-foreground">
                Hozircha video topshiriqlari yo‘q.
              </p>
            )}
          </div>
          <div className="mt-6 border-t border-border pt-4 text-xs text-muted-foreground">
            AI suhbatlari · 30 kun
            <div className="mt-3 flex justify-between">
              <span>Yakunlangan: {data?.assistant_completed ?? '—'}</span>
              <span>Xatolik: {data?.assistant_failed ?? '—'}</span>
            </div>
          </div>
        </section>
      </div>
      <div className="grid gap-5 xl:grid-cols-2">
        <section className="workspace-card">
          {data ? <PolicyForm policy={data.policy} /> : <p>Yuklanmoqda…</p>}
        </section>
        <section className="workspace-card">
          <h2 className="mb-4 font-semibold">Boshqaruv bo‘limlari</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            {adminNavItems
              .filter((item) => !item.roles || hasAnyRole(item.roles))
              .map((item) => (
                <Link
                  key={item.to}
                  to={item.to}
                  className="rounded-lg border border-border p-4 text-sm transition-colors hover:border-orange-400/40 hover:bg-muted"
                >
                  {t(item.labelKey)}{' '}
                  <span className="float-right text-orange-400">↗</span>
                </Link>
              ))}
          </div>
        </section>
      </div>
    </div>
  )
}

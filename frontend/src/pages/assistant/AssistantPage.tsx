import { LANGUAGES } from '@/i18n/registry'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { planningApi } from '@/api/planning'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { assistantApi, type Profile } from '@/api/assistant'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { ErrorState } from '@/components/common/StateViews'

const steps = [
  { key: 'channel', to: '/channel' },
  { key: 'preferences', to: '/preferences' },
  { key: 'plan', to: '/content-plan' },
  { key: 'videos', to: '/videos' },
  { key: 'revenue', to: '/revenue' },
]
function ProfileForm({ profile }: { profile: Profile }) {
  const { t } = useTranslation()
  const [form, setForm] = useState(profile)
  const cache = useQueryClient()
  const save = useMutation({
    mutationFn: () => assistantApi.profile({ ...form, onboarding_completed: true }),
    onSuccess: () => cache.invalidateQueries({ queryKey: ['assistant'] }),
  })
  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault()
        save.mutate()
      }}
    >
      <div>
        <h2 className="font-semibold">{t('assistant.profile.title')}</h2>
        <p className="mt-1 text-xs text-muted-foreground">
          {t('assistant.profile.subtitle')}
        </p>
      </div>
      <label className="block text-xs">
        {t('assistant.profile.goal')}
        <textarea
          required
          maxLength={1000}
          className="mt-2 min-h-24 w-full rounded-lg border border-border bg-background p-3 text-sm"
          value={form.goal}
          onChange={(e) => setForm({ ...form, goal: e.target.value })}
          placeholder={t('assistant.profile.goalPlaceholder')}
        />
      </label>
      <label className="block text-xs">
        {t('assistant.profile.region')}
        <Input
          className="mt-2"
          maxLength={100}
          value={form.audience_region}
          onChange={(e) => setForm({ ...form, audience_region: e.target.value })}
          placeholder={t('assistant.profile.regionPlaceholder')}
        />
      </label>
      <div className="grid grid-cols-2 gap-3">
        <label className="text-xs">
          {t('assistant.profile.language')}
          <select
            className="mt-2 w-full rounded-lg border border-border bg-background p-2.5"
            value={form.language}
            onChange={(e) => setForm({ ...form, language: e.target.value })}
          >
            {LANGUAGES.map((language) => (
              <option key={language.code} value={language.code}>
                {language.native_name}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs">
          {t('assistant.profile.timezone')}
          <Input
            className="mt-2"
            required
            value={form.timezone}
            onChange={(e) => setForm({ ...form, timezone: e.target.value })}
          />
        </label>
      </div>
      <Button disabled={save.isPending} type="submit" className="w-full">
        {save.isPending ? t('assistant.profile.saving') : t('assistant.profile.save')}
      </Button>
      {save.isSuccess && (
        <p role="status" className="text-xs text-emerald-500">
          {t('assistant.profile.saved')}
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
function PlanStarter({ channel, ready }: { channel?: string; ready: boolean }) {
  const { t } = useTranslation()
  const [count, setCount] = useState(3)
  const [key, setKey] = useState(() => crypto.randomUUID())
  const create = useMutation({
    mutationFn: () => planningApi.propose(channel!, 'weekly', count, key),
    onSuccess: () => setKey(crypto.randomUUID()),
  })
  return (
    <section className="workspace-card">
      <h2 className="font-semibold">{t('assistant.planner.title')}</h2>
      <p className="mt-2 text-xs leading-5 text-muted-foreground">
        {t('assistant.planner.description')}
      </p>
      <form
        className="mt-4 space-y-3"
        onSubmit={(e) => {
          e.preventDefault()
          create.mutate()
        }}
      >
        <label className="block text-xs">
          {t('assistant.planner.count')}
          <input
            type="number"
            min={1}
            max={7}
            required
            value={count}
            onChange={(e) => {
              setCount(Number(e.target.value))
              setKey(crypto.randomUUID())
            }}
            className="mt-2 w-full rounded-lg border border-border bg-background p-2.5"
          />
        </label>
        <Button
          className="w-full"
          disabled={!channel || !ready || create.isPending || create.isSuccess}
          type="submit"
        >
          {create.isPending
            ? t('assistant.planner.working')
            : t('assistant.planner.submit')}
        </Button>
      </form>
      {create.isError && (
        <p role="alert" className="mt-3 text-xs text-red-400">
          {create.error.message}
        </p>
      )}
      {create.isSuccess && (
        <Link className="mt-3 block text-sm text-orange-400 underline" to="/content-plan">
          {t('assistant.planner.review')}
        </Link>
      )}
      {!channel && (
        <Link className="mt-3 block text-xs underline" to="/channel">
          {t('assistant.planner.connectFirst')}
        </Link>
      )}
    </section>
  )
}
export function AssistantPage() {
  const { t } = useTranslation()
  const cache = useQueryClient()
  const query = useQuery({
    queryKey: ['assistant'],
    queryFn: assistantApi.state,
    refetchInterval: (q) =>
      q.state.data?.turns.some((t) => ['pending', 'running'].includes(t.status))
        ? 3000
        : false,
  })
  const [message, setMessage] = useState('')
  const [requestKey, setRequestKey] = useState(() => crypto.randomUUID())
  const send = useMutation({
    mutationFn: ({ text, key }: { text: string; key: string }) =>
      assistantApi.send(text, key),
    onSuccess: () => {
      setMessage('')
      setRequestKey(crypto.randomUUID())
      void cache.invalidateQueries({ queryKey: ['assistant'] })
    },
  })
  if (query.isError) return <ErrorState onRetry={() => query.refetch()} />
  if (!query.data)
    return (
      <div className="animate-pulse p-8 text-muted-foreground">
        {t('assistant.loading')}
      </div>
    )
  const data = query.data
  const busy =
    send.isPending || data.turns.some((t) => ['pending', 'running'].includes(t.status))
  const completed = [
    data.channels.some((c) => c.status === 'connected'),
    data.preferences.length > 0,
    data.plans.some((p) => p.status === 'approved'),
    data.jobs.some((j) => j.status === 'published' && j.count > 0),
  ]
  const stats: [string, string][] = [
    [
      t('assistant.stats.channel'),
      data.channels.some((c) => c.status === 'connected')
        ? t('assistant.stats.channelConnected')
        : t('assistant.stats.channelDisconnected'),
    ],
    [t('assistant.stats.plans'), String(data.plans.length)],
    [
      t('assistant.stats.limit'),
      t('assistant.stats.limitValue', { limit: data.daily_message_limit }),
    ],
  ]
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="workspace-eyebrow">{t('assistant.eyebrow')}</p>
          <h1 className="mt-1 text-2xl font-semibold">{t('assistant.title')}</h1>
          <p className="mt-1 text-sm text-muted-foreground">{t('assistant.subtitle')}</p>
        </div>
        <span
          className={`rounded-full border px-3 py-1.5 text-xs ${data.available ? 'text-emerald-500 border-emerald-500/30' : 'text-amber-500 border-amber-500/30'}`}
        >
          {data.available ? t('assistant.connected') : t('assistant.awaitingConnection')}
        </span>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        {stats.map(([label, value]) => (
          <div key={label} className="workspace-card">
            <p className="workspace-eyebrow">{label}</p>
            <p className="mt-3 text-xl font-semibold">{value}</p>
          </div>
        ))}
      </div>
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
        <section className="workspace-card flex min-h-[510px] flex-col !p-0">
          <div className="flex items-center gap-3 border-b border-border p-5">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-orange-500/15 font-semibold text-orange-400">
              AI
            </span>
            <div>
              <h2 className="font-semibold">{t('assistant.chat.title')}</h2>
              <p className="text-xs text-muted-foreground">
                {t('assistant.chat.subtitle')}
              </p>
            </div>
          </div>
          <div
            className="max-h-[540px] flex-1 space-y-5 overflow-y-auto p-5"
            aria-live="polite"
          >
            <div className="rounded-xl border border-border bg-muted/50 p-4 text-sm leading-7">
              {t('assistant.chat.welcome')}
            </div>
            {[...data.turns].reverse().map((turn) => (
              <div key={turn.id} className="space-y-3">
                <div className="ml-8 rounded-xl border border-orange-500/20 bg-orange-500/10 p-4 text-sm whitespace-pre-wrap">
                  {turn.question}
                </div>
                <div className="mr-4 rounded-xl bg-muted/60 p-4 text-sm leading-7 whitespace-pre-wrap">
                  {turn.status === 'completed'
                    ? turn.answer
                    : turn.status === 'failed'
                      ? t('assistant.chat.failed')
                      : t('assistant.chat.working')}
                </div>
                {turn.status === 'completed' && (
                  <p className="text-xs text-muted-foreground">
                    {t('assistant.chat.cost', { amount: turn.cost_usd })}
                  </p>
                )}
              </div>
            ))}
          </div>
          <form
            className="border-t border-border p-4"
            onSubmit={(e) => {
              e.preventDefault()
              if (message.trim()) send.mutate({ text: message, key: requestKey })
            }}
          >
            <label htmlFor="assistant-message" className="sr-only">
              {t('assistant.chat.inputLabel')}
            </label>
            <textarea
              id="assistant-message"
              maxLength={3000}
              value={message}
              onChange={(e) => {
                setMessage(e.target.value)
                setRequestKey(crypto.randomUUID())
              }}
              disabled={!data.available || busy}
              placeholder={
                data.available
                  ? t('assistant.chat.placeholder')
                  : t('assistant.chat.disabledPlaceholder')
              }
              className="min-h-20 w-full resize-y rounded-lg border border-border bg-background p-3 text-sm disabled:opacity-60"
            />
            <div className="mt-3 flex items-center justify-between gap-3">
              <p className="text-xs text-muted-foreground">
                {t('assistant.chat.disclaimer')}
              </p>
              <Button type="submit" disabled={!data.available || busy || !message.trim()}>
                {t('assistant.chat.send')}
              </Button>
            </div>
            {send.isError && (
              <p role="alert" className="mt-2 text-xs text-red-400">
                {send.error.message}
              </p>
            )}
          </form>
        </section>
        <aside className="space-y-5">
          <PlanStarter
            channel={data.channels.find((c) => c.status === 'connected')?.id}
            ready={data.available && data.preferences.length > 0}
          />
          <section className="workspace-card">
            <ProfileForm profile={data.profile} />
          </section>
          <section className="workspace-card">
            <h2 className="mb-4 font-semibold">{t('assistant.steps.title')}</h2>
            {steps.map((step, i) => (
              <Link
                key={step.to}
                to={step.to}
                className="flex gap-3 border-b border-border py-3 last:border-0"
              >
                <span
                  className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs ${completed[i] ? 'bg-emerald-500/15 text-emerald-500' : 'bg-muted text-muted-foreground'}`}
                >
                  {completed[i] ? '✓' : i + 1}
                </span>
                <div>
                  <p className="text-sm font-medium">
                    {t(`assistant.steps.${step.key}.title`)} ↗
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {t(`assistant.steps.${step.key}.detail`)}
                  </p>
                </div>
              </Link>
            ))}
          </section>
        </aside>
      </div>
    </div>
  )
}

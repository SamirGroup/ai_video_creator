import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '@/api/client'
import { adminApi } from '@/api/admin'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import type { Plan } from '@/types/billing'

function PlanEditor({ plan }: { plan: Plan }) {
  const client = useQueryClient()
  const providers = useQuery({
    queryKey: ['admin-providers'],
    queryFn: adminApi.listProviders,
  })
  const [videos, setVideos] = useState(String(plan.videos_per_period))
  const [jobBudget, setJobBudget] = useState(String(plan.features?.job_budget_usd ?? '1'))
  const [name, setName] = useState(plan.name)
  const [duration, setDuration] = useState(String(plan.max_video_duration_sec))
  const [active, setActive] = useState(plan.is_active)
  const [price, setPrice] = useState(plan.price_amount)
  const [discount, setDiscount] = useState(plan.discount_pct ?? '0')
  const [label, setLabel] = useState(plan.discount_label ?? '')
  const [end, setEnd] = useState(plan.discount_ends_at?.slice(0, 16) ?? '')
  const [stars, setStars] = useState(String(plan.stars_amount ?? 0))
  const [models, setModels] = useState(
    ((plan.features?.video_models as string[]) ?? []).join(', '),
  )
  const save = useMutation({
    mutationFn: () =>
      adminApi.updatePlan(plan.id, {
        name,
        videos_per_period: Number(videos),
        max_video_duration_sec: Number(duration),
        is_active: active,
        price_amount: price,
        discount_pct: discount,
        discount_label: label,
        discount_ends_at: end ? new Date(end).toISOString() : null,
        stars_amount: Number(stars),
        features: {
          ...plan.features,
          job_budget_usd: jobBudget,
          video_models: models
            .split(',')
            .map((v) => v.trim())
            .filter(Boolean),
        },
      }),
    onSuccess: () =>
      Promise.all(
        ['admin-plans', 'plans', 'video-models', 'planning-budget'].map((key) =>
          client.invalidateQueries({ queryKey: [key] }),
        ),
      ),
  })
  return (
    <form
      className="grid gap-3 rounded-xl border border-border p-4 sm:grid-cols-2"
      onSubmit={(e) => {
        e.preventDefault()
        save.mutate()
      }}
    >
      <h3 className="font-semibold sm:col-span-2">{plan.name} · 70% AI / 30% platform</h3>
      <Input label="Plan name" value={name} onChange={(e) => setName(e.target.value)} />
      <Input
        label="Maximum duration (seconds)"
        type="number"
        min="1"
        value={duration}
        onChange={(e) => setDuration(e.target.value)}
      />
      <label>
        <input
          type="checkbox"
          checked={active}
          onChange={(e) => setActive(e.target.checked)}
        />
        Available for new purchases
      </label>
      <Input
        label="Price before 12% tax (USD)"
        type="number"
        min="1"
        step="0.01"
        value={price}
        onChange={(e) => setPrice(e.target.value)}
      />
      <Input
        label="Discount (%)"
        type="number"
        min="0"
        max="100"
        value={discount}
        onChange={(e) => setDiscount(e.target.value)}
      />
      <Input
        label="Discount announcement"
        value={label}
        onChange={(e) => setLabel(e.target.value)}
      />
      <Input
        label="Discount ends (your local time)"
        type="datetime-local"
        value={end}
        onChange={(e) => setEnd(e.target.value)}
      />
      <Input
        label="Telegram Stars total (0 = disabled)"
        type="number"
        min="0"
        value={stars}
        onChange={(e) => setStars(e.target.value)}
      />
      <Input
        label="Monthly video limit / Oylik video limiti"
        type="number"
        min="1"
        required
        value={videos}
        onChange={(e) => setVideos(e.target.value)}
      />
      <Input
        label="Maximum AI spend per video (USD) / Video byudjeti"
        type="number"
        min="0.01"
        step="0.01"
        required
        value={jobBudget}
        onChange={(e) => setJobBudget(e.target.value)}
      />
      <fieldset className="space-y-2 rounded border border-border p-3 sm:col-span-2">
        <legend>Included AI models / Tarifga kiruvchi modellar</legend>
        {providers.isError && <p role="alert">Model catalog could not be loaded.</p>}
        {providers.data
          ?.filter((p) => p.service === 'video_gen')
          .map((provider) => {
            const id = provider.model_name || ''
            const selected = models
              .split(',')
              .map((v) => v.trim())
              .filter(Boolean)
            return (
              <label key={provider.id} className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={selected.includes(id)}
                  onChange={(e) =>
                    setModels(
                      (e.target.checked
                        ? [...new Set([...selected, id])]
                        : selected.filter((v) => v !== id)
                      ).join(', '),
                    )
                  }
                />
                {provider.display_name} · ${provider.unit_cost_usd} / {provider.cost_unit}{' '}
                · {provider.is_active ? 'Active' : 'Inactive'}
              </label>
            )
          })}
      </fieldset>
      <p className="text-sm sm:col-span-2">
        Oylik reja video limiti va bo‘sh AI balansidan hisoblanadi. Har video byudjeti
        qancha katta bo‘lsa, reja sig‘imi shuncha kamayadi. Tarif/model o‘zgarishi kelgusi
        generatsiyalarda yana tekshiriladi.
      </p>
      <p className="text-sm sm:col-span-2">
        New prices apply to new purchases. Existing Stripe subscriptions retain their
        agreed recurring price.
      </p>
      {save.isError && <p role="alert">{save.error.message}</p>}
      {save.isSuccess && <p role="status">Saved</p>}
      <Button isLoading={save.isPending}>Save plan</Button>
    </form>
  )
}
export function CommercialSettings() {
  const plans = useQuery({ queryKey: ['admin-plans'], queryFn: adminApi.listPlans })
  const cfg = useQuery({
    queryKey: ['telegram-config'],
    queryFn: () =>
      apiClient
        .get<{ enabled: boolean; channel_id: string; bot_username: string }>(
          '/admin/telegram',
        )
        .then((r) => r.data),
    retry: false,
  })
  const [rate, setRate] = useState('')
  const [channel, setChannel] = useState('')
  const [bot, setBot] = useState('')
  const [enabled, setEnabled] = useState(false)
  const save = useMutation({
    mutationFn: () =>
      apiClient.patch('/admin/telegram', {
        channel_id: channel,
        bot_username: bot,
        enabled,
        ...(rate ? { stars_net_usd: rate } : {}),
      }),
    onSuccess: () => cfg.refetch(),
  })
  return (
    <div className="space-y-5">
      <h2 className="text-lg font-semibold">Superadmin · Plans and Telegram</h2>
      {plans.data
        ?.filter((p) => p.ai_budget_enabled)
        .map((p) => (
          <PlanEditor key={p.id} plan={p} />
        ))}
      {cfg.data && (
        <form
          className="space-y-3 rounded-xl border border-border p-4"
          onSubmit={(e) => {
            e.preventDefault()
            save.mutate()
          }}
        >
          <p>
            Current archive: {cfg.data.channel_id || 'Not configured'} ·{' '}
            {cfg.data.enabled ? 'Active' : 'Inactive'}
          </p>
          <Input
            label="Private Telegram channel ID"
            placeholder="-100…"
            required
            value={channel}
            onChange={(e) => setChannel(e.target.value)}
          />
          <Input
            label="Verified net USD received per Star (0 disables Stars sales)"
            type="number"
            min="0"
            step="0.000001"
            value={rate}
            onChange={(e) => setRate(e.target.value)}
          />
          <Input
            label="Bot username"
            required
            value={bot}
            onChange={(e) => setBot(e.target.value)}
          />
          <label className="flex gap-2">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) => setEnabled(e.target.checked)}
            />
            Activate archive, webhook and Mini App menu
          </label>
          <p className="text-sm">
            Server environment: TELEGRAM_BOT_TOKEN, TELEGRAM_WEBHOOK_SECRET,
            TELEGRAM_WEBHOOK_BASE_URL. The bot must be an administrator of the private
            channel.
          </p>
          {save.isError && <p role="alert">{save.error.message}</p>}
          <Button isLoading={save.isPending}>Save Telegram configuration</Button>
        </form>
      )}
    </div>
  )
}

import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'
import { channelsApi } from '@/api/channels'
import { planningApi, type PlanItem } from '@/api/planning'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader, CardContent, CardTitle } from '@/components/ui/Card'
import { ErrorState, EmptyState, PageLoading } from '@/components/common/StateViews'

function EditablePlanItem({
  item,
  plan,
  editable,
  onChange,
}: {
  item: PlanItem
  plan: string
  editable: boolean
  onChange: () => void
}) {
  const { t, i18n } = useTranslation()
  const [title, setTitle] = useState(item.title)
  const [brief, setBrief] = useState(item.brief)
  const [scheduled, setScheduled] = useState('')
  const save = useMutation({
    mutationFn: () =>
      planningApi.update(plan, item.id, {
        title,
        brief,
        ...(scheduled ? { scheduled_for: new Date(scheduled).toISOString() } : {}),
      }),
    onSuccess: onChange,
  })
  const toggle = useMutation({
    mutationFn: () => planningApi.update(plan, item.id, { selected: !item.selected }),
    onSuccess: onChange,
  })
  return (
    <Card>
      <CardContent className="space-y-3 pt-5">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={item.selected}
            disabled={!editable || toggle.isPending}
            onChange={() => toggle.mutate()}
          />
          <span>{item.title}</span>
        </label>
        <p className="text-sm text-muted-foreground">{item.rationale}</p>
        <p className="text-sm">
          {new Intl.DateTimeFormat(i18n.resolvedLanguage, {
            dateStyle: 'medium',
            timeStyle: 'short',
          }).format(new Date(item.scheduled_for))}
        </p>
        {editable && (
          <details>
            <summary className="cursor-pointer text-primary-500">
              {t('planning.edit')}
            </summary>
            <div className="mt-3 flex flex-col gap-3">
              <input
                aria-label={t('video.table.title')}
                className="rounded border bg-surface p-2"
                maxLength={100}
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
              <textarea
                aria-label={t('planning.brief')}
                className="rounded border bg-surface p-2"
                maxLength={4000}
                value={brief}
                onChange={(e) => setBrief(e.target.value)}
              />
              <label>
                {t('planning.localTime')}
                <input
                  type="datetime-local"
                  className="ms-3 rounded border bg-surface p-2"
                  value={scheduled}
                  onChange={(e) => setScheduled(e.target.value)}
                />
              </label>
              <Button
                disabled={!title.trim() || !brief.trim()}
                isLoading={save.isPending}
                onClick={() => save.mutate()}
              >
                {t('common.save')}
              </Button>
            </div>
          </details>
        )}
        {(save.isError || toggle.isError) && <ErrorState />}
        {item.job && (
          <Link className="text-primary-500" to={`/videos/${item.job}`}>
            {t('video.title')} ↗
          </Link>
        )}
      </CardContent>
    </Card>
  )
}

export function ContentPlanPage() {
  const { t } = useTranslation()
  const client = useQueryClient()
  const [channel, setChannel] = useState('')
  const [horizon, setHorizon] = useState('weekly')
  const [count, setCount] = useState(3)
  const channels = useQuery({ queryKey: ['channels'], queryFn: channelsApi.list })
  const channelId = channel || channels.data?.[0]?.id || ''
  const plans = useQuery({
    queryKey: ['content-plans', channelId],
    queryFn: () => planningApi.list(channelId),
    enabled: !!channelId,
    refetchInterval: 5000,
  })
  const refresh = () =>
    client.invalidateQueries({ queryKey: ['content-plans', channelId] })
  const propose = useMutation({
    mutationFn: () => planningApi.propose(channelId, horizon, count, crypto.randomUUID()),
    onSuccess: refresh,
  })
  const approve = useMutation({
    mutationFn: ({ id, items }: { id: string; items: string[] }) =>
      planningApi.approve(id, items),
    onSuccess: async () => {
      await refresh()
      await client.invalidateQueries({ queryKey: ['videos'] })
    },
  })
  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold">{t('planning.title')}</h1>
      <p className="text-sm text-muted-foreground">{t('planning.explanation')}</p>
      <div className="flex flex-wrap items-end gap-3">
        <label>
          {t('channel.title')}
          <select
            className="ms-2 rounded border bg-surface p-2"
            value={channelId}
            onChange={(e) => setChannel(e.target.value)}
          >
            {channels.data?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.channel_title}
              </option>
            ))}
          </select>
        </label>
        <select
          aria-label={t('planning.period')}
          className="rounded border bg-surface p-2"
          value={horizon}
          onChange={(e) => {
            setHorizon(e.target.value)
            setCount(1)
          }}
        >
          {['daily', 'weekly', 'monthly'].map((h) => (
            <option key={h} value={h}>
              {t(`planning.${h}`)}
            </option>
          ))}
        </select>
        <input
          aria-label={t('planning.count')}
          className="w-20 rounded border bg-surface p-2"
          type="number"
          min={1}
          max={horizon === 'daily' ? 1 : horizon === 'weekly' ? 7 : 30}
          value={count}
          onChange={(e) => setCount(Number(e.target.value))}
        />
        <Button
          disabled={
            !channelId ||
            count < 1 ||
            plans.data?.some((p) => ['pending', 'generating'].includes(p.status))
          }
          isLoading={propose.isPending}
          onClick={() => propose.mutate()}
        >
          {t('planning.propose')}
        </Button>
      </div>
      {(plans.isError || channels.isError || propose.isError || approve.isError) && (
        <ErrorState />
      )}
      {plans.isLoading && <PageLoading />}
      {channels.data?.length === 0 && (
        <EmptyState description={t('dashboard.connectChannel')} />
      )}
      {plans.data?.map((plan) => (
        <Card key={plan.id}>
          <CardHeader>
            <CardTitle>
              {t(`planning.status.${plan.status}`)} ·{' '}
              {plan.preference_snapshot.publish_timezone}
            </CardTitle>
            <p>{plan.summary}</p>
          </CardHeader>
          <CardContent className="space-y-4">
            {plan.error_code && (
              <p role="alert" className="text-destructive-500">
                {t('planning.failed')} ({plan.error_code})
              </p>
            )}
            {plan.analysis.retrieved_at && (
              <p className="text-xs text-muted-foreground">
                YouTube · {new Date(plan.analysis.retrieved_at).toLocaleString()}
              </p>
            )}
            {plan.items.map((item) => (
              <EditablePlanItem
                key={`${item.id}:${item.title}:${item.brief}`}
                plan={plan.id}
                item={item}
                editable={plan.status === 'ready'}
                onChange={() => void refresh()}
              />
            ))}
            {plan.analysis.videos?.length ? (
              <details>
                <summary>{t('planning.sources')}</summary>
                <ul className="mt-2 space-y-2 text-sm">
                  {plan.analysis.videos.map((v) => (
                    <li key={v.video_id}>
                      <a
                        className="text-primary-500"
                        href={`https://www.youtube.com/watch?v=${encodeURIComponent(v.video_id)}`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        {v.title}
                      </a>{' '}
                      · {v.views.toLocaleString()} {t('revenue.views')}
                    </li>
                  ))}
                </ul>
              </details>
            ) : null}
            {plan.status === 'ready' && (
              <Button
                disabled={!plan.items.some((i) => i.selected)}
                isLoading={approve.isPending}
                onClick={() =>
                  approve.mutate({
                    id: plan.id,
                    items: plan.items.filter((i) => i.selected).map((i) => i.id),
                  })
                }
              >
                {t('planning.approve')}
              </Button>
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

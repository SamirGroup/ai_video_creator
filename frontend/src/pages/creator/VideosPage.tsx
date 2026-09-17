import { billingApi } from '@/api/billing'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { videosApi } from '@/api/videos'
import { channelsApi } from '@/api/channels'
import { useTranslation } from 'react-i18next'

import { ErrorState, TableSkeleton } from '@/components/common/StateViews'
import { Button } from '@/components/ui/Button'
import { VideoTable } from '@/components/video/VideoTable'
import { useVideoList } from '@/hooks/useVideos'

export function VideosPage() {
  const { t } = useTranslation()
  const client = useQueryClient()
  const [channelId, setChannelId] = useState('')
  const [model, setModel] = useState('')
  const subscription = useQuery({
    queryKey: ['subscription'],
    queryFn: billingApi.mySubscription,
  })
  const models = (subscription.data?.plan.features?.video_models ?? []) as string[]
  const channels = useQuery({ queryKey: ['channels'], queryFn: channelsApi.list })
  const generate = useMutation({
    mutationFn: () =>
      videosApi.generateNow(channelId || channels.data?.[0]?.id, model || models[0]),
    onSuccess: () => client.invalidateQueries({ queryKey: ['videos'] }),
  })
  const { data, isLoading, isError, refetch } = useVideoList()

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold text-foreground">{t('video.title')}</h1>
        {/* TODO: real API — POST /videos/generate (manual trigger, FR-36) */}
        <div className="flex flex-wrap gap-2">
          <select
            aria-label={t('channel.title')}
            className="rounded border border-border bg-surface p-2"
            value={channelId || channels.data?.[0]?.id || ''}
            onChange={(e) => setChannelId(e.target.value)}
          >
            {channels.data?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.channel_title}
              </option>
            ))}
          </select>
          {models.length > 0 && (
            <select
              aria-label="Video AI model"
              className="rounded border border-border bg-surface p-2"
              value={model || models[0]}
              onChange={(e) => setModel(e.target.value)}
            >
              {models.map((id) => (
                <option key={id} value={id}>
                  {id}
                </option>
              ))}
            </select>
          )}
          <Button
            size="sm"
            disabled={!channels.data?.length}
            isLoading={generate.isPending}
            onClick={() => generate.mutate()}
          >
            {t('video.generateNow')}
          </Button>
        </div>
      </div>

      {(generate.isError || channels.isError) && <ErrorState />}
      {isLoading && <TableSkeleton />}
      {isError && <ErrorState onRetry={() => refetch()} />}
      {data && <VideoTable videos={data} />}
    </div>
  )
}

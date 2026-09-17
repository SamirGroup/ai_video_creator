import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { CardSkeletonGrid, EmptyState, ErrorState } from '@/components/common/StateViews'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { channelsApi } from '@/api/channels'

// TODO: real API — replace with channelsApi.list()/getAdsenseAccount() (src/api/channels.ts)
function useChannel() {
  return useQuery({
    queryKey: ['channel'],
    queryFn: async () => (await channelsApi.list())[0] ?? null,
  })
}
function useAdsenseAccount() {
  return useQuery({
    queryKey: ['adsense-account'],
    queryFn: channelsApi.getAdsenseAccount,
  })
}

export function ChannelPage() {
  const { t } = useTranslation()
  const client = useQueryClient()
  const connect = useMutation({
    mutationFn: channelsApi.getYoutubeAuthorizeUrl,
    onSuccess: (data) => window.location.assign(data.authorization_url),
  })
  const connectAdsense = useMutation({
    mutationFn: channelsApi.getAdsenseAuthorizeUrl,
    onSuccess: (data) => window.location.assign(data.authorization_url),
  })
  const disconnect = useMutation({
    mutationFn: (id: string) => channelsApi.disconnect(id),
    onSuccess: async () => {
      setShowDisconnectConfirm(false)
      await client.invalidateQueries({ queryKey: ['channel'] })
      await client.invalidateQueries({ queryKey: ['channels'] })
    },
  })
  const channelQuery = useChannel()
  const adsenseQuery = useAdsenseAccount()
  const [showDisconnectConfirm, setShowDisconnectConfirm] = useState(false)

  return (
    <div className="flex flex-col gap-6">
      {(connect.isError ||
        connectAdsense.isError ||
        disconnect.isError ||
        adsenseQuery.isError) && <ErrorState />}
      <h1 className="text-xl font-semibold text-foreground">{t('channel.title')}</h1>

      {channelQuery.isLoading && <CardSkeletonGrid count={1} />}
      {channelQuery.isError && <ErrorState onRetry={() => channelQuery.refetch()} />}

      {channelQuery.data === null && (
        <EmptyState
          title={t('dashboard.disconnected')}
          description={t('dashboard.connectChannel')}
          action={
            // TODO: real API — GET /oauth/youtube/authorize then redirect (FR-10)
            <Button isLoading={connect.isPending} onClick={() => connect.mutate()}>
              {t('channel.connect')}
            </Button>
          }
        />
      )}

      {channelQuery.data && (
        <Card>
          <CardHeader className="flex-row items-center justify-between space-y-0">
            <div>
              <CardTitle className="text-base font-semibold text-foreground">
                {channelQuery.data.channel_title}
              </CardTitle>
              <p className="text-sm text-muted-foreground">
                {channelQuery.data.channel_handle}
              </p>
            </div>
            <Badge
              tone={channelQuery.data.status === 'connected' ? 'success' : 'destructive'}
              dot
            >
              {channelQuery.data.status}
            </Badge>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
              <div>
                <p className="text-xs text-muted-foreground">
                  {t('channel.subscribers')}
                </p>
                <p className="text-lg font-semibold text-foreground">
                  {channelQuery.data.subscriber_count?.toLocaleString()}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">{t('channel.videos')}</p>
                <p className="text-lg font-semibold text-foreground">
                  {channelQuery.data.video_count?.toLocaleString()}
                </p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">{t('common.status')}</p>
                <p className="text-sm text-foreground">
                  {channelQuery.data.is_monetized
                    ? t('channel.monetization.monetized')
                    : channelQuery.data.is_monetized === false
                      ? t('channel.monetization.notMonetized')
                      : t('channel.monetization.unknown')}
                </p>
              </div>
            </div>

            <div className="border-t border-border pt-4">
              <p className="mb-2 text-sm font-medium text-foreground">
                {t('channel.adsense.title')}
              </p>
              {adsenseQuery.isLoading && (
                <p className="text-sm text-muted-foreground">{t('common.loading')}</p>
              )}
              {adsenseQuery.data ? (
                <Badge tone="success" dot>
                  {t('channel.adsense.connected')}
                </Badge>
              ) : (
                adsenseQuery.isSuccess && (
                  <div className="flex items-center justify-between gap-3">
                    <Badge tone="neutral">{t('channel.adsense.notConnected')}</Badge>
                    {/* TODO: real API — GET /oauth/adsense/authorize (FR-19) */}
                    <Button
                      size="sm"
                      variant="outline"
                      isLoading={connectAdsense.isPending}
                      onClick={() => connectAdsense.mutate()}
                    >
                      {t('channel.adsense.connect')}
                    </Button>
                  </div>
                )
              )}
            </div>

            {showDisconnectConfirm ? (
              <div className="flex flex-col gap-2 rounded-md border border-destructive-600/40 bg-destructive-50 p-3 dark:bg-destructive-700/10">
                <p className="text-sm text-destructive-700 dark:text-destructive-500">
                  {t('channel.disconnectConfirm')}
                </p>
                <div className="flex justify-end gap-2">
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setShowDisconnectConfirm(false)}
                  >
                    {t('common.cancel')}
                  </Button>
                  {/* TODO: real API — DELETE /channels/{id} + Google token revoke (FR-15) */}
                  <Button
                    size="sm"
                    variant="destructive"
                    isLoading={disconnect.isPending}
                    onClick={() => disconnect.mutate(channelQuery.data!.id)}
                  >
                    {t('channel.disconnect')}
                  </Button>
                </div>
              </div>
            ) : (
              <div>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setShowDisconnectConfirm(true)}
                >
                  {t('channel.disconnect')}
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}

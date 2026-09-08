import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import { CardSkeletonGrid, ErrorState } from '@/components/common/StateViews'
import { Badge } from '@/components/ui/Badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { VideoTable } from '@/components/video/VideoTable'
import { mockDashboardSummary, mockVideos } from '@/mocks/fixtures'
import { mockFetch } from '@/mocks/mockFetch'
import { useAuth } from '@/hooks/useAuth'

// TODO: real API — replace with GET /me/subscription + /videos + /revenue/summary
// once the backend is live (see src/api/billing.ts, videos.ts, revenue.ts).
function useDashboardSummary() {
  return useQuery({
    queryKey: ['dashboard-summary'],
    queryFn: () => mockFetch(mockDashboardSummary),
  })
}

export function DashboardPage() {
  const { t, i18n } = useTranslation()
  const { user } = useAuth()
  const { data, isLoading, isError, refetch } = useDashboardSummary()

  const recentVideos = mockVideos.slice(0, 3)

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold text-foreground">{t('dashboard.title')}</h1>
        <p className="text-sm text-muted-foreground">
          {t('dashboard.welcome', { name: user?.full_name ?? user?.email ?? '' })}
        </p>
      </div>

      {isLoading && <CardSkeletonGrid />}
      {isError && <ErrorState onRetry={() => refetch()} />}

      {data && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Card>
            <CardHeader>
              <CardTitle>{t('dashboard.cards.channelStatus')}</CardTitle>
            </CardHeader>
            <CardContent>
              <Badge tone={data.channelConnected ? 'success' : 'warning'} dot>
                {data.channelConnected ? t('dashboard.connected') : t('dashboard.disconnected')}
              </Badge>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{t('dashboard.cards.videosThisMonth')}</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-semibold text-foreground">
                {data.videosThisMonth}
                <span className="text-sm font-normal text-muted-foreground">
                  {' '}
                  / {data.videoQuota}
                </span>
              </p>
              <p className="text-xs text-muted-foreground">
                {t('dashboard.quotaUsed', {
                  used: data.videosThisMonth,
                  total: data.videoQuota,
                })}
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{t('dashboard.cards.estimatedRevenue')}</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-2xl font-semibold text-foreground">
                {new Intl.NumberFormat(i18n.resolvedLanguage ?? 'en', {
                  style: 'currency',
                  currency: 'USD',
                }).format(Number(data.estimatedRevenueUsd))}
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>{t('dashboard.cards.pendingApprovals')}</CardTitle>
            </CardHeader>
            <CardContent className="flex items-center justify-between">
              <p className="text-2xl font-semibold text-foreground">{data.pendingApprovals}</p>
              {data.pendingApprovals > 0 && (
                <Link
                  to="/videos"
                  className="inline-flex h-8 items-center rounded-md border border-border px-3 text-sm font-medium text-foreground transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
                >
                  {t('video.title')}
                </Link>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      <div className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold text-foreground">{t('nav.videos')}</h2>
        <VideoTable videos={recentVideos} />
      </div>
    </div>
  )
}

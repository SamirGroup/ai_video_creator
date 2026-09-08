import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router-dom'

import { EmptyState, ErrorState, PageLoading } from '@/components/common/StateViews'
import { Card, CardContent } from '@/components/ui/Card'
import { ApprovalActions } from '@/components/video/ApprovalActions'
import { VideoStatusBadge } from '@/components/video/VideoStatusBadge'
import {
  useApproveVideo,
  useRejectVideo,
  useRequestChangesVideo,
  useVideoDetail,
  useVideoSteps,
} from '@/hooks/useVideos'

export function VideoDetailPage() {
  const { t, i18n } = useTranslation()
  const { videoId = '' } = useParams<{ videoId: string }>()
  const videoQuery = useVideoDetail(videoId)
  const stepsQuery = useVideoSteps(videoId)

  const approveMutation = useApproveVideo(videoId)
  const requestChangesMutation = useRequestChangesVideo(videoId)
  const rejectMutation = useRejectVideo(videoId)

  if (videoQuery.isLoading) return <PageLoading />
  if (videoQuery.isError) return <ErrorState onRetry={() => videoQuery.refetch()} />
  if (!videoQuery.data) {
    return <EmptyState title={t('video.empty.title')} description={t('video.empty.description')} />
  }

  const video = videoQuery.data

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Link to="/videos" className="text-sm text-primary-600 hover:underline">
          ← {t('common.back')}
        </Link>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-foreground">
            {video.title ?? t('common.unknown')}
          </h1>
          <p className="text-sm text-muted-foreground">
            {new Intl.DateTimeFormat(i18n.resolvedLanguage ?? 'en', {
              dateStyle: 'medium',
              timeStyle: 'short',
            }).format(new Date(video.scheduled_for))}
          </p>
        </div>
        <VideoStatusBadge status={video.status} />
      </div>

      {video.preview_url && (
        <Card>
          <CardContent className="pt-5">
            <p className="mb-2 text-sm font-medium text-foreground">{t('video.approval.preview')}</p>
            <div className="flex aspect-video items-center justify-center rounded-md bg-muted text-sm text-muted-foreground">
              {/* TODO: real API — signed preview URL from GET /videos/{id}/preview */}
              {t('video.previewPlaceholder')}
            </div>
          </CardContent>
        </Card>
      )}

      {video.status === 'awaiting_approval' && (
        <Card>
          <CardContent className="flex flex-col gap-4 pt-5">
            <h2 className="text-sm font-semibold text-foreground">{t('video.approval.title')}</h2>
            <ApprovalActions
              onApprove={() => approveMutation.mutate()}
              onRequestChanges={(payload) => requestChangesMutation.mutate(payload)}
              onReject={(payload) => rejectMutation.mutate(payload)}
              isApproving={approveMutation.isPending}
              isRequestingChanges={requestChangesMutation.isPending}
              isRejecting={rejectMutation.isPending}
            />
          </CardContent>
        </Card>
      )}

      {video.error_message && (
        <Card className="border-destructive-600/40">
          <CardContent className="pt-5">
            <p className="text-sm font-medium text-destructive-700 dark:text-destructive-500">
              {video.error_code}
            </p>
            <p className="text-sm text-muted-foreground">{video.error_message}</p>
          </CardContent>
        </Card>
      )}

      <div>
        <h2 className="mb-3 text-sm font-semibold text-foreground">{t('video.steps')}</h2>
        {stepsQuery.isLoading && <PageLoading />}
        {stepsQuery.data && stepsQuery.data.length === 0 && (
          <EmptyState title={t('common.empty.title')} />
        )}
        {stepsQuery.data && stepsQuery.data.length > 0 && (
          <ol className="flex flex-col gap-2">
            {stepsQuery.data.map((step) => (
              <li
                key={step.id}
                className="flex items-center justify-between rounded-md border border-border p-3 text-sm"
              >
                <span className="font-medium text-foreground">{step.stage}</span>
                <span className="text-muted-foreground">{step.provider}</span>
                <span className="text-muted-foreground">${step.cost_usd}</span>
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  )
}

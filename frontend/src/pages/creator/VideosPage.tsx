import { useTranslation } from 'react-i18next'

import { ErrorState, TableSkeleton } from '@/components/common/StateViews'
import { Button } from '@/components/ui/Button'
import { VideoTable } from '@/components/video/VideoTable'
import { useVideoList } from '@/hooks/useVideos'

export function VideosPage() {
  const { t } = useTranslation()
  const { data, isLoading, isError, refetch } = useVideoList()

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold text-foreground">{t('video.title')}</h1>
        {/* TODO: real API — POST /videos/generate (manual trigger, FR-36) */}
        <Button size="sm">{t('video.generateNow')}</Button>
      </div>

      {isLoading && <TableSkeleton />}
      {isError && <ErrorState onRetry={() => refetch()} />}
      {data && <VideoTable videos={data} />}
    </div>
  )
}

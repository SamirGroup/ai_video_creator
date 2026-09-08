import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { ErrorState, TableSkeleton } from '@/components/common/StateViews'
import { Button } from '@/components/ui/Button'
import { VideoStatusBadge } from '@/components/video/VideoStatusBadge'
import { mockAdminVideos } from '@/mocks/fixtures'
import { mockFetch } from '@/mocks/mockFetch'

// TODO: real API — replace with adminApi.listVideoJobs (src/api/admin.ts)
function useAdminVideos() {
  return useQuery({ queryKey: ['admin-videos'], queryFn: () => mockFetch(mockAdminVideos) })
}

export function AdminVideosPage() {
  const { t } = useTranslation()
  const { data, isLoading, isError, refetch } = useAdminVideos()

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold text-foreground">{t('admin.videos.title')}</h1>

      {isLoading && <TableSkeleton />}
      {isError && <ErrorState onRetry={() => refetch()} />}

      {data && (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead className="border-b border-border bg-muted/50 text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="px-4 py-3 font-medium">{t('video.table.title')}</th>
                <th className="px-4 py-3 font-medium">User</th>
                <th className="px-4 py-3 font-medium">{t('video.table.status')}</th>
                <th className="px-4 py-3 text-right font-medium">{t('common.actions')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {data.map((job) => (
                <tr key={job.id}>
                  <td className="max-w-64 truncate px-4 py-3 font-medium text-foreground">
                    {job.title ?? t('common.unknown')}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{job.user_email}</td>
                  <td className="px-4 py-3">
                    <VideoStatusBadge status={job.status} />
                  </td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex justify-end gap-2">
                      {/* TODO: real API — POST /admin/videos/{id}/retry|cancel */}
                      <Button size="sm" variant="outline">
                        {t('admin.videos.retry')}
                      </Button>
                      <Button size="sm" variant="ghost">
                        {t('admin.videos.cancel')}
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import { VideoStatusBadge } from './VideoStatusBadge'
import { EmptyState } from '@/components/common/StateViews'
import type { VideoJob } from '@/types/video'

function formatDate(iso: string, locale: string) {
  return new Intl.DateTimeFormat(locale, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(iso))
}

function formatCost(amount: string, locale: string) {
  return new Intl.NumberFormat(locale, { style: 'currency', currency: 'USD' }).format(
    Number(amount),
  )
}

export function VideoTable({
  videos,
  basePath = '/videos',
}: {
  videos: VideoJob[]
  basePath?: string
}) {
  const { t, i18n } = useTranslation()

  if (videos.length === 0) {
    return (
      <EmptyState
        title={t('video.empty.title')}
        description={t('video.empty.description')}
      />
    )
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full min-w-[640px] text-start text-sm">
        <thead className="border-b border-border bg-muted/50 text-xs uppercase tracking-wide text-muted-foreground">
          <tr>
            <th scope="col" className="px-4 py-3 font-medium">
              {t('video.table.title')}
            </th>
            <th scope="col" className="px-4 py-3 font-medium">
              {t('video.table.status')}
            </th>
            <th scope="col" className="px-4 py-3 font-medium">
              {t('video.table.scheduledFor')}
            </th>
            <th scope="col" className="px-4 py-3 font-medium">
              {t('video.table.cost')}
            </th>
            <th scope="col" className="px-4 py-3 text-end font-medium">
              {t('video.table.actions')}
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {videos.map((video) => (
            <tr key={video.id} className="transition-colors hover:bg-muted/40">
              <td className="max-w-64 truncate px-4 py-3 font-medium text-foreground">
                {video.title ?? t('common.unknown')}
              </td>
              <td className="px-4 py-3">
                <VideoStatusBadge status={video.status} />
              </td>
              <td className="px-4 py-3 text-muted-foreground">
                {formatDate(video.scheduled_for, i18n.resolvedLanguage ?? 'en')}
              </td>
              <td className="px-4 py-3 text-muted-foreground">
                {formatCost(video.total_cost_usd, i18n.resolvedLanguage ?? 'en')}
              </td>
              <td className="px-4 py-3 text-end">
                <Link
                  to={`${basePath}/${video.id}`}
                  className="rounded text-sm font-medium text-primary-600 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  {t('video.approval.preview')}
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

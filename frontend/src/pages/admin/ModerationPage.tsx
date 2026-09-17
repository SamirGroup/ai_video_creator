import { adminApi } from '@/api/admin'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { EmptyState, ErrorState, TableSkeleton } from '@/components/common/StateViews'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'

function useModerationQueue() {
  return useQuery({
    queryKey: ['moderation-queue'],
    queryFn: adminApi.allModeration,
  })
}

export function ModerationPage() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { data, isLoading, isError, refetch } = useModerationQueue()
  const [reasonByJob, setReasonByJob] = useState<Record<string, string>>({})

  const decideMutation = useMutation({
    mutationFn: ({
      jobId,
      decision,
    }: {
      jobId: string
      decision: 'approved' | 'rejected'
    }) =>
      adminApi.decideModerationCase(jobId, {
        decision,
        reason: reasonByJob[jobId] ?? '',
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['moderation-queue'] }),
  })

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold text-foreground">
        {t('admin.moderation.title')}
      </h1>

      {decideMutation.isError && <ErrorState />}
      {isLoading && <TableSkeleton rows={2} />}
      {isError && <ErrorState onRetry={() => refetch()} />}
      {data && data.length === 0 && <EmptyState />}

      {data && data.length > 0 && (
        <div className="flex flex-col gap-3">
          {data.map((item) => {
            const reason = reasonByJob[item.job_id] ?? ''
            return (
              <div
                key={item.job_id}
                className="flex flex-col gap-3 rounded-lg border border-border p-4"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="text-sm font-medium text-foreground">
                      {item.video_title}
                    </p>
                    <p className="text-xs text-muted-foreground">{item.user_email}</p>
                  </div>
                  <Badge tone="warning" dot>
                    {item.verdict}
                  </Badge>
                </div>
                <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                  {Object.entries(item.categories).map(([category, score]) => (
                    <span key={category} className="rounded bg-muted px-2 py-1">
                      {category}: {(score * 100).toFixed(0)}%
                    </span>
                  ))}
                </div>
                <textarea
                  rows={2}
                  placeholder={t('admin.moderation.reasonRequired')}
                  value={reason}
                  onChange={(e) =>
                    setReasonByJob((prev) => ({ ...prev, [item.job_id]: e.target.value }))
                  }
                  className="rounded-md border border-border bg-surface p-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                />
                <div className="flex justify-end gap-2">
                  <Button
                    size="sm"
                    variant="destructive"
                    disabled={!reason.trim()}
                    isLoading={decideMutation.isPending}
                    onClick={() =>
                      decideMutation.mutate({ jobId: item.job_id, decision: 'rejected' })
                    }
                  >
                    {t('admin.moderation.reject')}
                  </Button>
                  <Button
                    size="sm"
                    disabled={!reason.trim()}
                    isLoading={decideMutation.isPending}
                    onClick={() =>
                      decideMutation.mutate({ jobId: item.job_id, decision: 'approved' })
                    }
                  >
                    {t('admin.moderation.approve')}
                  </Button>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

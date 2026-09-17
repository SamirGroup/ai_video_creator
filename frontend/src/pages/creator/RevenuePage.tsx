import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import {
  CardSkeletonGrid,
  ErrorState,
  TableSkeleton,
} from '@/components/common/StateViews'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { revenueApi } from '@/api/revenue'
import { downloadFile } from '@/lib/download'
import type { StatementStatus } from '@/types/revenue'

function useRevenueSummary() {
  return useQuery({ queryKey: ['revenue-summary'], queryFn: () => revenueApi.summary() })
}
function useRevenueByVideo() {
  return useQuery({ queryKey: ['revenue-by-video'], queryFn: () => revenueApi.byVideo() })
}
function useStatements() {
  return useQuery({ queryKey: ['revenue-statements'], queryFn: revenueApi.statements })
}

const statementTone: Record<
  StatementStatus,
  'neutral' | 'success' | 'warning' | 'destructive'
> = {
  draft: 'neutral',
  finalized: 'neutral',
  invoiced: 'warning',
  paid: 'success',
  disputed: 'destructive',
  written_off: 'destructive',
  carried_forward: 'neutral',
}

export function RevenuePage() {
  const { t, i18n } = useTranslation()
  const client = useQueryClient()
  const [now, setNow] = useState(Date.now)
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 60000)
    return () => window.clearInterval(timer)
  }, [])
  const [disputeId, setDisputeId] = useState<string | null>(null)
  const [reason, setReason] = useState('')
  const dispute = useMutation({
    mutationFn: () => revenueApi.dispute(disputeId!, { reason }),
    onSuccess: async () => {
      setDisputeId(null)
      setReason('')
      await client.invalidateQueries({ queryKey: ['revenue-statements'] })
    },
  })
  const download = useMutation({
    mutationFn: (id: string) =>
      downloadFile(`/revenue/statements/${id}/pdf`, `statement-${id}.pdf`),
  })
  const summaryQuery = useRevenueSummary()
  const byVideoQuery = useRevenueByVideo()
  const statementsQuery = useStatements()

  const currencyFmt = (value: string) =>
    new Intl.NumberFormat(i18n.resolvedLanguage ?? 'en', {
      style: 'currency',
      currency: 'USD',
    }).format(Number(value))

  return (
    <div className="flex flex-col gap-6">
      {download.isError && <ErrorState />}
      {disputeId && (
        <form
          className="rounded-lg border border-border p-4"
          onSubmit={(event) => {
            event.preventDefault()
            dispute.mutate()
          }}
        >
          <label htmlFor="dispute-reason">{t('revenue.disputeReason')}</label>
          <textarea
            id="dispute-reason"
            className="my-3 block w-full rounded border border-border bg-background p-3"
            required
            maxLength={2000}
            value={reason}
            onChange={(event) => setReason(event.target.value)}
          />
          {dispute.isError && <ErrorState />}
          <Button type="submit" disabled={!reason.trim()} isLoading={dispute.isPending}>
            {t('revenue.dispute')}
          </Button>
          <Button type="button" variant="ghost" onClick={() => setDisputeId(null)}>
            {t('common.cancel')}
          </Button>
        </form>
      )}
      <h1 className="text-xl font-semibold text-foreground">{t('revenue.title')}</h1>

      {summaryQuery.isLoading && <CardSkeletonGrid count={3} />}
      {summaryQuery.isError && <ErrorState onRetry={() => summaryQuery.refetch()} />}

      {summaryQuery.data && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <Card>
            <CardHeader>
              <CardTitle>{t('revenue.totalViews')}</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-lg font-semibold text-foreground">
                {summaryQuery.data.total_views.toLocaleString()}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>{t('dashboard.cards.estimatedRevenue')}</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-lg font-semibold text-foreground">
                {currencyFmt(summaryQuery.data.total_estimated_revenue)}
              </p>
              <Badge tone={summaryQuery.data.is_estimated ? 'warning' : 'success'} dot>
                {summaryQuery.data.is_estimated
                  ? t('revenue.estimated')
                  : t('revenue.confirmed')}
              </Badge>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>{t('revenue.topVideos')}</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-lg font-semibold text-foreground">
                {byVideoQuery.data?.length ?? '—'}
              </p>
            </CardContent>
          </Card>
        </div>
      )}

      <div>
        <h2 className="mb-3 text-sm font-semibold text-foreground">
          {t('revenue.topVideos')}
        </h2>
        {byVideoQuery.isError && <ErrorState onRetry={() => byVideoQuery.refetch()} />}
        {byVideoQuery.isLoading && <TableSkeleton rows={3} />}
        {byVideoQuery.data && (
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full min-w-[480px] text-start text-sm">
              <tbody className="divide-y divide-border">
                {byVideoQuery.data.map((row) => (
                  <tr key={row.job_id}>
                    <td className="max-w-64 truncate px-4 py-3 font-medium text-foreground">
                      {row.title}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {row.views.toLocaleString()} {t('revenue.views')}
                    </td>
                    <td className="px-4 py-3 text-end text-foreground">
                      {currencyFmt(row.estimated_revenue)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div>
        <h2 className="mb-3 text-sm font-semibold text-foreground">
          {t('revenue.statements')}
        </h2>
        {statementsQuery.isLoading && <TableSkeleton rows={2} />}
        {statementsQuery.isError && (
          <ErrorState onRetry={() => statementsQuery.refetch()} />
        )}
        {statementsQuery.data && (
          <div className="flex flex-col gap-2">
            {statementsQuery.data.map((statement) => (
              <Card key={statement.id}>
                <CardContent className="flex flex-wrap items-center justify-between gap-3 pt-5">
                  <div>
                    <p className="text-sm font-medium text-foreground">
                      {statement.period_start} — {statement.period_end}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {t('revenue.title')}: {currencyFmt(statement.creator_share_amount)}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    {statement.review_deadline && (
                      <span className="text-xs text-muted-foreground">
                        {t('revenue.reviewUntil', {
                          date: new Date(statement.review_deadline).toLocaleString(
                            i18n.resolvedLanguage,
                          ),
                        })}
                      </span>
                    )}
                    {['draft', 'finalized', 'invoiced', 'paid'].includes(
                      statement.status,
                    ) &&
                      ((statement.review_deadline &&
                        new Date(statement.review_deadline).getTime() > now) ||
                        (!statement.review_deadline &&
                          statement.finalized_at &&
                          now - new Date(statement.finalized_at).getTime() <
                            14 * 86400000)) && (
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => {
                            setDisputeId(statement.id)
                            setReason('')
                          }}
                        >
                          {t('revenue.dispute')}
                        </Button>
                      )}
                    <Badge tone={statementTone[statement.status]} dot>
                      {t(`revenue.statementStatus.${statement.status}`)}
                    </Badge>
                    <Button
                      size="sm"
                      variant="outline"
                      isLoading={download.isPending}
                      onClick={() => download.mutate(statement.id)}
                    >
                      PDF
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

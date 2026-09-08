import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { CardSkeletonGrid, ErrorState, TableSkeleton } from '@/components/common/StateViews'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { mockRevenueByVideo, mockRevenueSummary, mockStatements } from '@/mocks/fixtures'
import { mockFetch } from '@/mocks/mockFetch'
import type { StatementStatus } from '@/types/revenue'

// TODO: real API — replace with revenueApi.summary/byVideo/statements (src/api/revenue.ts)
function useRevenueSummary() {
  return useQuery({ queryKey: ['revenue-summary'], queryFn: () => mockFetch(mockRevenueSummary) })
}
function useRevenueByVideo() {
  return useQuery({ queryKey: ['revenue-by-video'], queryFn: () => mockFetch(mockRevenueByVideo) })
}
function useStatements() {
  return useQuery({ queryKey: ['revenue-statements'], queryFn: () => mockFetch(mockStatements) })
}

const statementTone: Record<StatementStatus, 'neutral' | 'success' | 'warning' | 'destructive'> = {
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
  const summaryQuery = useRevenueSummary()
  const byVideoQuery = useRevenueByVideo()
  const statementsQuery = useStatements()

  const currencyFmt = (value: string) =>
    new Intl.NumberFormat(i18n.resolvedLanguage ?? 'en', { style: 'currency', currency: 'USD' }).format(
      Number(value),
    )

  return (
    <div className="flex flex-col gap-6">
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
                {summaryQuery.data.is_estimated ? t('revenue.estimated') : t('revenue.confirmed')}
              </Badge>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>{t('revenue.topVideos')}</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-lg font-semibold text-foreground">{byVideoQuery.data?.length ?? '—'}</p>
            </CardContent>
          </Card>
        </div>
      )}

      <div>
        <h2 className="mb-3 text-sm font-semibold text-foreground">{t('revenue.topVideos')}</h2>
        {byVideoQuery.isLoading && <TableSkeleton rows={3} />}
        {byVideoQuery.data && (
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full min-w-[480px] text-left text-sm">
              <tbody className="divide-y divide-border">
                {byVideoQuery.data.map((row) => (
                  <tr key={row.job_id}>
                    <td className="max-w-64 truncate px-4 py-3 font-medium text-foreground">
                      {row.title}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {row.views.toLocaleString()} {t('revenue.views')}
                    </td>
                    <td className="px-4 py-3 text-right text-foreground">
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
        <h2 className="mb-3 text-sm font-semibold text-foreground">{t('revenue.statements')}</h2>
        {statementsQuery.isLoading && <TableSkeleton rows={2} />}
        {statementsQuery.isError && <ErrorState onRetry={() => statementsQuery.refetch()} />}
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
                  <div className="flex items-center gap-2">
                    <Badge tone={statementTone[statement.status]} dot>
                      {t(`revenue.statementStatus.${statement.status}`)}
                    </Badge>
                    {/* TODO: real API — GET /revenue/statements/{id}/pdf */}
                    <Button size="sm" variant="outline">
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

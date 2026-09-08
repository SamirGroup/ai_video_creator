import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { ErrorState, TableSkeleton } from '@/components/common/StateViews'
import { Badge } from '@/components/ui/Badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'
import { mockProviders } from '@/mocks/fixtures'
import { mockFetch } from '@/mocks/mockFetch'

// TODO: real API — replace with adminApi.listProviders() (src/api/admin.ts).
// Plan configuration (adminApi.listPlans/updatePlan) is deferred until the
// billing app ships its Plan CRUD endpoints — this page renders providers only.
function useProviders() {
  return useQuery({
    queryKey: ['admin-providers'],
    queryFn: () => mockFetch(mockProviders),
  })
}

export function AdminConfigPage() {
  const { t } = useTranslation()
  const { data, isLoading, isError, refetch } = useProviders()

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold text-foreground">{t('admin.config.title')}</h1>

      <Card>
        <CardHeader>
          <CardTitle>{t('admin.config.providers')}</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading && (
            <div className="p-4 sm:p-5">
              <TableSkeleton rows={4} />
            </div>
          )}
          {isError && (
            <div className="p-4 sm:p-5">
              <ErrorState onRetry={() => refetch()} />
            </div>
          )}

          {data && (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-left text-sm">
                <thead className="border-b border-t border-border bg-muted/50 text-xs uppercase tracking-wide text-muted-foreground">
                  <tr>
                    <th className="px-4 py-3 font-medium">Service</th>
                    <th className="px-4 py-3 font-medium">Provider</th>
                    <th className="px-4 py-3 font-medium">Model</th>
                    <th className="px-4 py-3 font-medium">{t('common.status')}</th>
                    <th className="px-4 py-3 font-medium">Unit cost</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {data.map((provider) => (
                    <tr key={provider.id}>
                      <td className="px-4 py-3 text-muted-foreground">{provider.service}</td>
                      <td className="px-4 py-3">
                        <p className="font-medium text-foreground">{provider.display_name}</p>
                        {provider.model_name && (
                          <p className="text-xs text-muted-foreground">{provider.model_name}</p>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        {provider.is_primary && <Badge tone="info">primary</Badge>}
                      </td>
                      <td className="px-4 py-3">
                        <Badge tone={provider.is_active ? 'success' : 'destructive'} dot>
                          {provider.is_active ? 'active' : 'inactive'}
                        </Badge>
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {provider.unit_cost_usd
                          ? `$${provider.unit_cost_usd} / ${provider.cost_unit}`
                          : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* TODO: real API — GET/PATCH /admin/plans (adminApi.listPlans/updatePlan) once
          the billing app exposes Plan CRUD endpoints (SPEC FR-83). */}
      <Card>
        <CardHeader>
          <CardTitle>{t('admin.config.plans')}</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">Coming soon.</p>
        </CardContent>
      </Card>
    </div>
  )
}

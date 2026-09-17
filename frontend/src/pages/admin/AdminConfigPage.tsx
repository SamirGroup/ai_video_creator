import { ProviderPriceEditor } from './ProviderPriceEditor'
import { CommercialSettings } from './CommercialSettings'
import { adminApi } from '@/api/admin'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'

import { ErrorState, TableSkeleton } from '@/components/common/StateViews'
import { Badge } from '@/components/ui/Badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card'

// Plan configuration (adminApi.listPlans/updatePlan) is deferred until the
// billing app ships its Plan CRUD endpoints — this page renders providers only.
function useProviders() {
  return useQuery({
    queryKey: ['admin-providers'],
    queryFn: adminApi.listProviders,
  })
}

export function AdminConfigPage() {
  const { t } = useTranslation()
  const { data, isLoading, isError, refetch } = useProviders()

  const plans = useQuery({ queryKey: ['admin-plans'], queryFn: adminApi.listPlans })
  const update = useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) =>
      adminApi.updateProvider(id, { is_active: active }),
    onSuccess: () => refetch(),
  })

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold text-foreground">{t('admin.config.title')}</h1>

      <CommercialSettings />
      <ProviderPriceEditor />
      {update.isError && <ErrorState />}
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
              <table className="w-full min-w-[720px] text-start text-sm">
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
                      <td className="px-4 py-3 text-muted-foreground">
                        {provider.service}
                      </td>
                      <td className="px-4 py-3">
                        <p className="font-medium text-foreground">
                          {provider.display_name}
                        </p>
                        {provider.model_name && (
                          <p className="text-xs text-muted-foreground">
                            {provider.model_name}
                          </p>
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
                        <input
                          type="checkbox"
                          aria-label={provider.display_name}
                          checked={provider.is_active}
                          disabled={update.isPending}
                          onChange={(e) =>
                            update.mutate({ id: provider.id, active: e.target.checked })
                          }
                        />{' '}
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

      <Card>
        <CardHeader>
          <CardTitle>{t('admin.config.plans')}</CardTitle>
        </CardHeader>
        <CardContent>
          {plans.isError && <ErrorState />}
          {plans.data?.map((plan) => (
            <div
              className="flex justify-between border-b border-border py-3"
              key={plan.id}
            >
              <span>{plan.name}</span>
              <span>
                {plan.price_amount} {plan.currency} · {plan.videos_per_period}{' '}
                {t('channel.videos')}
              </span>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  )
}

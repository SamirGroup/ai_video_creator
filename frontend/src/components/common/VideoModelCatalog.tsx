import { useQuery } from '@tanstack/react-query'
import { apiClient } from '@/api/client'
import { useTranslation } from 'react-i18next'
import { ErrorState } from './StateViews'
export interface VideoModelPrice {
  model: string
  name: string
  provider: string
  price_usd: string
  unit: string
  credits_per_unit: number
  available: boolean
  source: string
  verified_on: string
  note: string
  plans: string[]
}
export function VideoModelCatalog() {
  const { t } = useTranslation()
  const query = useQuery({
    queryKey: ['video-models'],
    queryFn: () => apiClient.get<VideoModelPrice[]>('/video-models').then((r) => r.data),
  })
  return (
    <section className="space-y-4 rounded-2xl border border-border bg-surface p-5">
      <h2 className="text-xl font-semibold">
        {t('modelCatalog.title', 'AI model prices')}
      </h2>
      <p className="text-sm text-muted-foreground">
        {t(
          'modelCatalog.note',
          'Video generation is billed per second. Credits are platform balance, not model tokens. Voice, scripts and revisions also consume credit.',
        )}
      </p>
      {query.isError && <ErrorState />}
      {query.isPending && <p role="status">{t('common.loading', 'Loading…')}</p>}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[680px] text-left text-sm">
          <thead>
            <tr className="border-b border-border text-muted-foreground">
              {['Model', 'USD / unit', 'Credits / unit', 'Plans', 'Availability'].map(
                (h) => (
                  <th key={h} className="p-3">
                    {t(`modelCatalog.${h}`, h)}
                  </th>
                ),
              )}
            </tr>
          </thead>
          <tbody>
            {query.data?.map((row) => (
              <tr key={`${row.provider}:${row.model}`} className="border-b border-border">
                <td className="p-3">
                  <strong>{row.name}</strong>
                  <div className="text-xs text-muted-foreground">
                    {row.provider} · {row.verified_on}
                  </div>
                  {row.source.startsWith('https://') && (
                    <a
                      className="text-primary-500"
                      href={row.source}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {t('modelCatalog.source', 'Pricing source')} ↗
                    </a>
                  )}
                </td>
                <td className="bg-primary-500/10 p-3 font-semibold text-primary-700">
                  ${Number(row.price_usd).toFixed(4)}
                  <div className="text-xs">{t(`modelCatalog.${row.unit}`, row.unit)}</div>
                </td>
                <td className="p-3">{row.credits_per_unit}</td>
                <td className="p-3">{row.plans.join(' · ') || '—'}</td>
                <td className="p-3">
                  {row.available
                    ? t('modelCatalog.ready', 'Ready')
                    : t('modelCatalog.pending', 'Configuration pending')}
                  <div className="text-xs text-muted-foreground">{row.provider === 'higgsfield' ? t('modelCatalog.launchOffer', 'Launch offer; verify before activation.') : row.note}</div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

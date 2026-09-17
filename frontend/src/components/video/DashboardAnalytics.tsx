import { useTranslation } from 'react-i18next'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/Card'
import { EmptyState } from '@/components/common/StateViews'
import type { RevenueDailyPoint } from '@/types/revenue'

export function DashboardAnalytics({ days }: { days: RevenueDailyPoint[] }) {
  const { t, i18n } = useTranslation()
  if (!days.length)
    return (
      <Card>
        <CardContent className="pt-5">
          <EmptyState />
        </CardContent>
      </Card>
    )
  const revenueMax = Math.max(1, ...days.map((d) => Number(d.estimated_revenue)))
  const viewsMax = Math.max(1, ...days.map((d) => d.views))
  const points = days
    .map(
      (day, i) =>
        `${35 + (i / Math.max(1, days.length - 1)) * 490},${200 - (Number(day.estimated_revenue) / revenueMax) * 165}`,
    )
    .join(' ')
  const total = days.reduce((sum, day) => sum + Number(day.estimated_revenue), 0)
  return (
    <div className="dashboard-analytics">
      <Card>
        <CardHeader>
          <CardTitle>{t('dashboard.analyticsTitle')}</CardTitle>
          <p className="text-2xl font-semibold">
            {new Intl.NumberFormat(i18n.resolvedLanguage, {
              style: 'currency',
              currency: 'USD',
            }).format(total)}
          </p>
          <p className="text-xs text-muted-foreground">{t('revenue.estimated')}</p>
        </CardHeader>
        <CardContent>
          <svg
            viewBox="0 0 560 230"
            role="img"
            aria-label={t('dashboard.analyticsTitle')}
          >
            <defs>
              <linearGradient id="revenue-fill" x1="0" y1="0" x2="0" y2="1">
                <stop stopColor="#8951ff" stopOpacity=".4" />
                <stop offset="1" stopColor="#8951ff" stopOpacity="0" />
              </linearGradient>
            </defs>
            {[35, 90, 145, 200].map((y) => (
              <line
                key={y}
                x1="35"
                x2="540"
                y1={y}
                y2={y}
                stroke="var(--color-border)"
                strokeDasharray="3 6"
              />
            ))}
            <polygon points={`35,200 ${points} 525,200`} fill="url(#revenue-fill)" />
            <polyline
              points={points}
              fill="none"
              stroke="#b44bff"
              strokeWidth="2.5"
              strokeLinejoin="round"
            />
            {days.map((day, i) => (
              <circle
                key={day.date}
                cx={35 + (i / Math.max(1, days.length - 1)) * 490}
                cy={200 - (Number(day.estimated_revenue) / revenueMax) * 165}
                r="3"
                fill="#b44bff"
              >
                <title>
                  {day.date}: ${day.estimated_revenue}
                </title>
              </circle>
            ))}
          </svg>
          <div className="flex justify-between text-xs text-muted-foreground">
            <span>{days[0].date}</span>
            <span>{days.at(-1)?.date}</span>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>{t('dashboard.activityTitle')}</CardTitle>
          <p className="text-2xl font-semibold">
            {days
              .reduce((sum, d) => sum + d.views, 0)
              .toLocaleString(i18n.resolvedLanguage)}
          </p>
        </CardHeader>
        <CardContent>
          <div
            className="dashboard-bars"
            role="img"
            aria-label={t('dashboard.activityTitle')}
          >
            {days.map((day) => (
              <div key={day.date} title={`${day.date}: ${day.views}`}>
                <span
                  style={{
                    height: `${(day.views / viewsMax) * 100}%`,
                    background: '#21c3fc',
                    width: '100%',
                  }}
                />
              </div>
            ))}
          </div>
          <div className="mt-3 flex justify-between text-xs text-muted-foreground">
            <span>{days[0].date}</span>
            <span>{days.at(-1)?.date}</span>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

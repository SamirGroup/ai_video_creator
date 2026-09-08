import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/Button'
import { Skeleton } from '@/components/ui/Skeleton'
import { Spinner } from '@/components/ui/Spinner'

/**
 * Standard states for any data-driven screen: loading / error / empty /
 * unauthorized (401) / forbidden (403) / offline. Every page that fetches
 * data should render one of these instead of a blank screen (skill
 * 39-frontend-api-state-contracts).
 */

export function PageLoading({ label }: { label?: string }) {
  const { t } = useTranslation()
  return (
    <div className="flex min-h-40 flex-col items-center justify-center gap-3 py-12 text-muted-foreground">
      <Spinner />
      <p className="text-sm">{label ?? t('common.loading')}</p>
    </div>
  )
}

export function CardSkeletonGrid({ count = 4 }: { count?: number }) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {Array.from({ length: count }).map((_, i) => (
        <Skeleton key={i} className="h-28 w-full" />
      ))}
    </div>
  )
}

export function TableSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="flex flex-col gap-2">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-12 w-full" />
      ))}
    </div>
  )
}

interface StateBlockProps {
  title: string
  description?: string
  action?: ReactNode
  icon?: ReactNode
}

function StateBlock({ title, description, action, icon }: StateBlockProps) {
  return (
    <div
      role="status"
      className="flex min-h-52 flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border p-8 text-center"
    >
      {icon}
      <p className="text-sm font-medium text-foreground">{title}</p>
      {description && <p className="max-w-sm text-sm text-muted-foreground">{description}</p>}
      {action}
    </div>
  )
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title?: string
  description?: string
  action?: ReactNode
}) {
  const { t } = useTranslation()
  return (
    <StateBlock
      title={title ?? t('common.empty.title')}
      description={description ?? t('common.empty.description')}
      action={action}
    />
  )
}

export function ErrorState({
  description,
  onRetry,
}: {
  description?: string
  onRetry?: () => void
}) {
  const { t } = useTranslation()
  return (
    <StateBlock
      title={t('common.error.title')}
      description={description ?? t('common.error.description')}
      action={
        onRetry && (
          <Button variant="outline" size="sm" onClick={onRetry}>
            {t('common.retry')}
          </Button>
        )
      }
    />
  )
}

export function UnauthorizedState() {
  const { t } = useTranslation()
  return (
    <StateBlock
      title={t('common.unauthorized.title')}
      description={t('common.unauthorized.description')}
    />
  )
}

export function ForbiddenState() {
  const { t } = useTranslation()
  return (
    <StateBlock
      title={t('common.forbidden.title')}
      description={t('common.forbidden.description')}
    />
  )
}

export function OfflineState({ onRetry }: { onRetry?: () => void }) {
  const { t } = useTranslation()
  return (
    <StateBlock
      title={t('common.offline.title')}
      description={t('common.offline.description')}
      action={
        onRetry && (
          <Button variant="outline" size="sm" onClick={onRetry}>
            {t('common.retry')}
          </Button>
        )
      }
    />
  )
}

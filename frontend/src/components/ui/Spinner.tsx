import { useTranslation } from 'react-i18next'

import { cn } from '@/lib/cn'

export function Spinner({ className }: { className?: string }) {
  const { t } = useTranslation()
  return (
    <span
      role="status"
      aria-label={t('common.loading')}
      className={cn(
        'inline-block h-5 w-5 animate-spin rounded-full border-2 border-current border-t-transparent text-primary-600',
        className,
      )}
    />
  )
}

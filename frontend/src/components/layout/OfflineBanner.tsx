import { useTranslation } from 'react-i18next'

import { useOnlineStatus } from '@/hooks/useOnlineStatus'

export function OfflineBanner() {
  const isOnline = useOnlineStatus()
  const { t } = useTranslation()

  if (isOnline) return null

  return (
    <div
      role="status"
      className="flex items-center justify-center gap-2 bg-warning-500 px-4 py-1.5 text-center text-xs font-medium text-white"
    >
      {t('common.offline.title')} — {t('common.offline.description')}
    </div>
  )
}

import { useTranslation } from 'react-i18next'

import type { NumberPrice } from '@/api/virtualNumbers'

export function NumberPriceBreakdown({ price }: { price?: NumberPrice | null }) {
  const { t } = useTranslation()
  if (!price?.base_cost) return null
  return (
    <dl className="my-3 space-y-1 text-sm">
      <div className="flex justify-between gap-3">
        <dt>{t('numbers.price.base')}</dt>
        <dd>${price.base_cost}</dd>
      </div>
      <div className="flex justify-between gap-3">
        <dt>{t('numbers.price.margin', { pct: Number(price.profit_pct) })}</dt>
        <dd>${price.profit}</dd>
      </div>
      <div className="flex justify-between gap-3">
        <dt>{t('numbers.price.tax', { pct: Number(price.tax_pct) })}</dt>
        <dd>${price.tax}</dd>
      </div>
      <div className="flex justify-between gap-3 border-t border-border pt-2 font-semibold">
        <dt>{t('numbers.price.total')}</dt>
        <dd>${price.total}</dd>
      </div>
      <div className="text-xs text-muted-foreground">
        {t('numbers.price.note', {
          basis:
            price.tax_basis === 'base'
              ? t('numbers.price.basisBase')
              : t('numbers.price.basisWithMargin'),
        })}
      </div>
    </dl>
  )
}

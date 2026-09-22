import type { NumberPrice } from '@/api/virtualNumbers'

export function NumberPriceBreakdown({ price }: { price?: NumberPrice | null }) {
  if (!price?.base_cost) return null
  return (
    <dl className="my-3 space-y-1 text-sm">
      <div className="flex justify-between gap-3">
        <dt>Provayder narxi</dt>
        <dd>${price.base_cost}</dd>
      </div>
      <div className="flex justify-between gap-3">
        <dt>Platforma ustamasi ({Number(price.profit_pct)}%)</dt>
        <dd>${price.profit}</dd>
      </div>
      <div className="flex justify-between gap-3">
        <dt>Soliq ({Number(price.tax_pct)}%)</dt>
        <dd>${price.tax}</dd>
      </div>
      <div className="flex justify-between gap-3 border-t border-border pt-2 font-semibold">
        <dt>Jami to‘lov</dt>
        <dd>${price.total}</dd>
      </div>
      <div className="text-xs text-muted-foreground">
        Soliq bazasi:{' '}
        {price.tax_basis === 'base'
          ? 'provayder narxi'
          : 'provayder narxi + platforma ustamasi'}
        . Narx USD’da.
      </div>
    </dl>
  )
}

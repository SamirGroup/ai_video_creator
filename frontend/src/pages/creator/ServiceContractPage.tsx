import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, Printer } from 'lucide-react'
import { adminWebServicesApi, webServicesApi } from '@/api/webServices'
import { ContractDocument } from '@/components/common/ContractDocument'
import { Button } from '@/components/ui/Button'

/** Full-page contract, outside the app shell so it prints as a clean A4. */
export function ServiceContractPage({ admin = false }: { admin?: boolean }) {
  const { t } = useTranslation()
  const { id = '' } = useParams()
  const order = useQuery({
    queryKey: ['web-service-order', admin, id],
    queryFn: () => (admin ? adminWebServicesApi.order(id) : webServicesApi.order(id)),
    gcTime: 0,
  })
  return (
    <div className="min-h-screen bg-neutral-200 py-6 dark:bg-neutral-900 print:bg-white print:py-0">
      <div className="mx-auto mb-4 flex max-w-[210mm] flex-wrap items-center justify-between gap-3 px-4 print:hidden">
        <Link
          to={admin ? '/admin/web-services' : '/web-services'}
          className="inline-flex items-center gap-2 text-sm hover:underline"
        >
          <ArrowLeft size={16} aria-hidden />
          {t('webServices.contract.back')}
        </Link>
        <Button onClick={() => window.print()} disabled={!order.data}>
          <Printer size={16} aria-hidden />
          {t('webServices.contract.print')}
        </Button>
      </div>
      {order.isPending && (
        <p className="text-center">{t('webServices.contract.loading')}</p>
      )}
      {order.isError && (
        <p role="alert" className="text-center">
          {t('webServices.contract.failed')}
        </p>
      )}
      {order.data?.contract && (
        <div className="px-2 sm:px-4 print:px-0">
          <ContractDocument doc={order.data.contract} />
        </div>
      )}
    </div>
  )
}

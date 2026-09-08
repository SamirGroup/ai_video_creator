import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { useTranslation } from 'react-i18next'
import { z } from 'zod'

import { CardSkeletonGrid, ErrorState } from '@/components/common/StateViews'
import { Button } from '@/components/ui/Button'
import { Card, CardContent } from '@/components/ui/Card'
import { Checkbox } from '@/components/ui/Checkbox'
import { mockContractVersion, mockSignedContracts, mockSubscription } from '@/mocks/fixtures'
import { mockFetch } from '@/mocks/mockFetch'

const consentSchema = z.object({
  consent_revenue_share: z.literal(true),
  consent_publish_to_channel: z.literal(true),
  consent_data_processing: z.literal(true),
  consent_marketing: z.boolean().optional(),
})

type ConsentFormValues = z.infer<typeof consentSchema>

// TODO: real API — replace with contractsApi.current/history/sign (src/api/contracts.ts)
function useContractVersion() {
  return useQuery({ queryKey: ['contract-current'], queryFn: () => mockFetch(mockContractVersion) })
}
function useContractHistory() {
  return useQuery({ queryKey: ['contract-history'], queryFn: () => mockFetch(mockSignedContracts) })
}
function useHasPaymentMethod() {
  return useQuery({
    queryKey: ['subscription-payment-method'],
    queryFn: () => mockFetch(Boolean(mockSubscription.default_payment_method_id)),
  })
}

export function ContractPage() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const versionQuery = useContractVersion()
  const historyQuery = useContractHistory()
  const hasPaymentMethodQuery = useHasPaymentMethod()

  const { register, handleSubmit } = useForm<ConsentFormValues>({
    resolver: zodResolver(consentSchema),
    defaultValues: {
      consent_revenue_share: false as unknown as true,
      consent_publish_to_channel: false as unknown as true,
      consent_data_processing: false as unknown as true,
      consent_marketing: false,
    },
  })

  const signMutation = useMutation({
    mutationFn: () => mockFetch({ ...mockSignedContracts[0], id: `c_${Date.now()}` }, 500),
    onSuccess: (signed) =>
      queryClient.setQueryData(['contract-history'], (list: typeof mockSignedContracts = []) => [
        signed,
        ...list,
      ]),
  })

  const alreadySigned = historyQuery.data?.some(
    (c) => c.contract_version_id === versionQuery.data?.id && c.status === 'active',
  )

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold text-foreground">{t('contract.title')}</h1>

      {versionQuery.isLoading && <CardSkeletonGrid count={1} />}
      {versionQuery.isError && <ErrorState onRetry={() => versionQuery.refetch()} />}

      {versionQuery.data && (
        <Card>
          <CardContent className="flex flex-col gap-4 pt-5">
            <div>
              <p className="text-sm font-medium text-foreground">
                {t('contract.currentVersion')}: v{versionQuery.data.version}
              </p>
              <p className="text-xs text-muted-foreground">{versionQuery.data.title}</p>
            </div>

            <div className="max-h-48 overflow-y-auto rounded-md border border-border bg-muted/40 p-3 text-sm text-muted-foreground whitespace-pre-line">
              {versionQuery.data.body_markdown}
            </div>

            {alreadySigned ? (
              <p role="status" className="text-sm text-success-700">
                {t('common.confirm')} ✓
              </p>
            ) : (
              <form
                className="flex flex-col gap-3"
                onSubmit={handleSubmit(() => signMutation.mutate())}
                noValidate
              >
                <Checkbox
                  label={t('contract.consentRevenueShare')}
                  {...register('consent_revenue_share')}
                />
                <Checkbox
                  label={t('contract.consentPublish')}
                  {...register('consent_publish_to_channel')}
                />
                <Checkbox
                  label={t('contract.consentDataProcessing')}
                  {...register('consent_data_processing')}
                />
                <Checkbox
                  label={t('contract.consentMarketing')}
                  {...register('consent_marketing')}
                />

                {hasPaymentMethodQuery.data === false && (
                  <p role="alert" className="text-sm text-destructive-600">
                    {t('contract.paymentMethodRequired')}
                  </p>
                )}

                <div>
                  <Button
                    type="submit"
                    isLoading={signMutation.isPending}
                    disabled={hasPaymentMethodQuery.data === false}
                  >
                    {t('contract.sign')}
                  </Button>
                </div>
              </form>
            )}
          </CardContent>
        </Card>
      )}

      <div>
        <h2 className="mb-3 text-sm font-semibold text-foreground">{t('contract.history')}</h2>
        {historyQuery.data && historyQuery.data.length > 0 && (
          <ul className="flex flex-col gap-2">
            {historyQuery.data.map((signed) => (
              <li
                key={signed.id}
                className="flex items-center justify-between rounded-md border border-border p-3 text-sm"
              >
                <span className="text-foreground">v{signed.version}</span>
                <span className="text-muted-foreground">
                  {new Date(signed.signed_at).toLocaleDateString()}
                </span>
                <a href={signed.pdf_url ?? '#'} className="text-primary-600 hover:underline">
                  {t('contract.downloadPdf')}
                </a>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useForm } from 'react-hook-form'
import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { z } from 'zod'

import { CardSkeletonGrid, ErrorState } from '@/components/common/StateViews'
import { Button } from '@/components/ui/Button'
import { Card, CardContent } from '@/components/ui/Card'
import { Checkbox } from '@/components/ui/Checkbox'
import { contractsApi } from '@/api/contracts'

const consentSchema = z.object({
  consent_revenue_share: z.literal(true),
  consent_publish_to_channel: z.literal(true),
  consent_data_processing: z.literal(true),
  consent_marketing: z.boolean().optional(),
})

type ConsentFormValues = z.infer<typeof consentSchema>

export function ContractPage() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const stateQuery = useQuery({
    queryKey: ['contract-current'],
    queryFn: contractsApi.current,
  })
  const versionQuery = { ...stateQuery, data: stateQuery.data?.version }
  const historyQuery = useQuery({
    queryKey: ['contract-history'],
    queryFn: contractsApi.history,
  })
  const hasPaymentMethodQuery = { data: stateQuery.data?.has_payment_method }

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<ConsentFormValues>({
    resolver: zodResolver(consentSchema),
    defaultValues: {
      consent_revenue_share: false as unknown as true,
      consent_publish_to_channel: false as unknown as true,
      consent_data_processing: false as unknown as true,
      consent_marketing: false,
    },
  })

  const signMutation = useMutation({
    mutationFn: (values: ConsentFormValues) => {
      if (!versionQuery.data) throw new Error(t('common.error.generic'))
      return contractsApi.sign({
        ...values,
        consent_marketing: values.consent_marketing ?? false,
        contract_version_id: versionQuery.data.id,
      })
    },
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['contract-history'] }),
        queryClient.invalidateQueries({ queryKey: ['contract-current'] }),
      ])
    },
  })
  const downloadMutation = useMutation({
    mutationFn: async (id: string) => {
      const blob = await contractsApi.downloadPdf(id)
      const url = URL.createObjectURL(blob)
      const link = document.createElement('a')
      link.href = url
      link.download = `contract-${id}.pdf`
      link.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    },
  })

  const alreadySigned = stateQuery.data?.signed ?? false
  useEffect(() => {
    reset({
      consent_revenue_share: false as unknown as true,
      consent_publish_to_channel: false as unknown as true,
      consent_data_processing: false as unknown as true,
      consent_marketing: false,
    })
  }, [versionQuery.data?.id, reset])

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
                onSubmit={handleSubmit((values) => signMutation.mutate(values))}
                noValidate
              >
                <Checkbox
                  label={t('contract.consentRevenueShare', {
                    platform: versionQuery.data.revenue_share_platform_pct,
                    creator: versionQuery.data.revenue_share_creator_pct,
                  })}
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

                {(signMutation.isError || Object.keys(errors).length > 0) && (
                  <p role="alert">
                    {signMutation.error?.message ?? t('common.error.generic')}
                  </p>
                )}
                <div>
                  <Button
                    type="submit"
                    isLoading={signMutation.isPending}
                    disabled={!hasPaymentMethodQuery.data || stateQuery.isFetching}
                  >
                    {t('contract.sign')}
                  </Button>
                </div>
              </form>
            )}
          </CardContent>
        </Card>
      )}

      {stateQuery.isSuccess && !versionQuery.data && <p>{t('common.empty.title')}</p>}
      {historyQuery.isError && <ErrorState onRetry={() => historyQuery.refetch()} />}
      {downloadMutation.isError && <p role="alert">{downloadMutation.error.message}</p>}
      <div>
        <h2 className="mb-3 text-sm font-semibold text-foreground">
          {t('contract.history')}
        </h2>
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
                {signed.pdf_url && (
                  <button
                    type="button"
                    disabled={downloadMutation.isPending}
                    onClick={() => downloadMutation.mutate(signed.id)}
                    className="text-primary-600 hover:underline"
                  >
                    {t('contract.downloadPdf')}
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

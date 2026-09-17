import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { apiClient, ApiError } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'

export function SettlementForm() {
  const { t } = useTranslation()
  const client = useQueryClient()
  const [job, setJob] = useState('')
  const [month, setMonth] = useState('')
  const [amount, setAmount] = useState('')
  const [evidence, setEvidence] = useState('')
  const save = useMutation({
    mutationFn: () => {
      const [year, selectedMonth] = month.split('-').map(Number)
      const next = new Date(Date.UTC(year, selectedMonth, 1)).toISOString().slice(0, 10)
      return apiClient.post('/admin/finance/settlements', {
        job_id: job.trim(),
        period_start: `${month}-01`,
        period_end: next,
        amount,
        evidence_reference: evidence.trim(),
      })
    },
    onSuccess: async () => {
      setJob('')
      setAmount('')
      setEvidence('')
      await client.invalidateQueries({ queryKey: ['admin-finance-overview'] })
    },
  })
  return (
    <form
      className="grid gap-4 rounded-xl border border-border bg-card p-5 sm:grid-cols-2"
      onSubmit={(event) => {
        event.preventDefault()
        save.mutate()
      }}
    >
      <h2 className="font-semibold sm:col-span-2">
        {t('admin.finance.settlementTitle')}
      </h2>
      <p className="text-sm text-muted-foreground sm:col-span-2">
        {t('admin.finance.settlementHelp')}
      </p>
      <Input
        label={t('admin.finance.videoId')}
        required
        value={job}
        onChange={(event) => setJob(event.target.value)}
      />
      <Input
        label={t('admin.finance.month')}
        type="month"
        required
        value={month}
        onChange={(event) => setMonth(event.target.value)}
      />
      <Input
        label={t('admin.finance.verifiedAmount')}
        type="number"
        min="0"
        step="0.0001"
        required
        value={amount}
        onChange={(event) => setAmount(event.target.value)}
      />
      <Input
        label={t('admin.finance.evidence')}
        required
        minLength={10}
        maxLength={500}
        value={evidence}
        onChange={(event) => setEvidence(event.target.value)}
      />
      {save.isError && (
        <p role="alert" className="text-destructive-600 sm:col-span-2">
          {save.error instanceof ApiError
            ? save.error.message
            : t('common.error.generic')}
        </p>
      )}
      {save.isSuccess && <p role="status">{t('admin.finance.settlementSaved')}</p>}
      <Button type="submit" isLoading={save.isPending}>
        {t('common.save')}
      </Button>
    </form>
  )
}

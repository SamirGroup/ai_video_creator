import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Button } from '@/components/ui/Button'
import { Select } from '@/components/ui/Select'
import type { RegenerationStage, RejectVideoPayload, RequestChangesPayload } from '@/types/video'

type Mode = 'idle' | 'request-changes' | 'reject'

export interface ApprovalActionsProps {
  onApprove: () => void
  onRequestChanges: (payload: RequestChangesPayload) => void
  onReject: (payload: RejectVideoPayload) => void
  isApproving?: boolean
  isRequestingChanges?: boolean
  isRejecting?: boolean
  /** Blocks all actions, e.g. while the job isn't in `awaiting_approval` anymore. */
  disabled?: boolean
}

const STAGES: RegenerationStage[] = ['script', 'voice', 'visuals']

/** Approve / Request changes / Reject flow for an `awaiting_approval` video job (FR-38..FR-41). */
export function ApprovalActions({
  onApprove,
  onRequestChanges,
  onReject,
  isApproving,
  isRequestingChanges,
  isRejecting,
  disabled,
}: ApprovalActionsProps) {
  const { t } = useTranslation()
  const [mode, setMode] = useState<Mode>('idle')
  const [reason, setReason] = useState('')
  const [regenerateFrom, setRegenerateFrom] = useState<RegenerationStage>('script')

  const isBusy = isApproving || isRequestingChanges || isRejecting

  function reset() {
    setMode('idle')
    setReason('')
  }

  if (mode === 'request-changes' || mode === 'reject') {
    const isReject = mode === 'reject'
    return (
      <form
        className="flex flex-col gap-3 rounded-lg border border-border p-4"
        onSubmit={(e) => {
          e.preventDefault()
          if (!reason.trim()) return
          if (isReject) {
            onReject({ reason })
          } else {
            onRequestChanges({ reason, regenerate_from: regenerateFrom })
          }
        }}
      >
        <div className="flex flex-col gap-1.5">
          <label htmlFor="approval-reason" className="text-sm font-medium text-foreground">
            {t('video.approval.reasonLabel')}
            <span className="text-destructive-600" aria-hidden="true">
              {' '}
              *
            </span>
          </label>
          <textarea
            id="approval-reason"
            required
            rows={3}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className="rounded-md border border-border bg-surface p-3 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
        </div>
        {!isReject && (
          <Select
            label={t('video.approval.regenerateFrom')}
            value={regenerateFrom}
            onChange={(e) => setRegenerateFrom(e.target.value as RegenerationStage)}
            options={STAGES.map((stage) => ({
              value: stage,
              label: t(`video.approval.stages.${stage}`),
            }))}
          />
        )}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="ghost" size="sm" onClick={reset} disabled={isBusy}>
            {t('common.cancel')}
          </Button>
          <Button
            type="submit"
            size="sm"
            variant={isReject ? 'destructive' : 'primary'}
            isLoading={isReject ? isRejecting : isRequestingChanges}
            disabled={disabled}
          >
            {isReject ? t('video.approval.reject') : t('video.approval.requestChanges')}
          </Button>
        </div>
      </form>
    )
  }

  return (
    <div className="flex flex-wrap gap-2">
      <Button
        variant="primary"
        onClick={onApprove}
        isLoading={isApproving}
        disabled={disabled || isBusy}
      >
        {t('video.approval.approve')}
      </Button>
      <Button
        variant="outline"
        onClick={() => setMode('request-changes')}
        disabled={disabled || isBusy}
      >
        {t('video.approval.requestChanges')}
      </Button>
      <Button
        variant="destructive"
        onClick={() => setMode('reject')}
        disabled={disabled || isBusy}
      >
        {t('video.approval.reject')}
      </Button>
    </div>
  )
}

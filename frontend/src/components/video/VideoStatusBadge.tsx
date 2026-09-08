import { useTranslation } from 'react-i18next'

import { Badge, type BadgeTone } from '@/components/ui/Badge'
import type { VideoJobStatus } from '@/types/video'

/** Maps every SPEC 7.2 status to a semantic tone (non-color cues via `dot`, WCAG 1.4.1). */
const STATUS_TONE: Record<VideoJobStatus, BadgeTone> = {
  draft: 'neutral',
  scheduled: 'neutral',
  queued: 'neutral',
  generating_script: 'info',
  script_ready: 'info',
  moderating_script: 'info',
  generating_voice: 'info',
  voice_ready: 'info',
  generating_visuals: 'info',
  visuals_ready: 'info',
  assembling: 'info',
  assembled: 'info',
  moderating_final: 'info',
  moderation_review: 'warning',
  moderation_rejected: 'destructive',
  awaiting_approval: 'warning',
  approved: 'success',
  changes_requested: 'warning',
  rejected: 'destructive',
  expired: 'destructive',
  upload_queued: 'info',
  uploading: 'info',
  uploaded: 'success',
  published: 'success',
  youtube_rejected: 'destructive',
  retrying: 'warning',
  failed: 'destructive',
  canceled: 'neutral',
  deleted_on_youtube: 'destructive',
}

export function VideoStatusBadge({ status }: { status: VideoJobStatus }) {
  const { t } = useTranslation()
  return (
    <Badge tone={STATUS_TONE[status]} dot>
      {t(`video.status.${status}`)}
    </Badge>
  )
}

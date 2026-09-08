/**
 * Mirrors `video_jobs.status` state machine (SPEC 7.2).
 * Terminal statuses: published, rejected, moderation_rejected, youtube_rejected,
 * expired, failed, canceled.
 */
export type VideoJobStatus =
  | 'draft'
  | 'scheduled'
  | 'queued'
  | 'generating_script'
  | 'script_ready'
  | 'moderating_script'
  | 'generating_voice'
  | 'voice_ready'
  | 'generating_visuals'
  | 'visuals_ready'
  | 'assembling'
  | 'assembled'
  | 'moderating_final'
  | 'moderation_review'
  | 'moderation_rejected'
  | 'awaiting_approval'
  | 'approved'
  | 'changes_requested'
  | 'rejected'
  | 'expired'
  | 'upload_queued'
  | 'uploading'
  | 'uploaded'
  | 'published'
  | 'youtube_rejected'
  | 'retrying'
  | 'failed'
  | 'canceled'
  | 'deleted_on_youtube'

export type VideoJobStage =
  | 'script'
  | 'voice'
  | 'visuals'
  | 'assembly'
  | 'moderation'
  | 'upload'

export type VideoJobTrigger = 'scheduled' | 'manual' | 'regeneration'

/** Mirrors `video_jobs` (SPEC 5.11) — the fields the creator/admin UI needs. */
export interface VideoJob {
  id: string
  channel_id: string
  trigger: VideoJobTrigger
  status: VideoJobStatus
  current_stage: VideoJobStage | null
  scheduled_for: string
  title: string | null
  description: string | null
  tags: string[]
  language: string
  duration_sec: number | null
  thumbnail_s3_key: string | null
  preview_url: string | null
  preview_expires_at: string | null
  approval_requested_at: string | null
  regeneration_count: number
  youtube_video_id: string | null
  youtube_url: string | null
  published_at: string | null
  error_code: string | null
  error_message: string | null
  total_cost_usd: string
  created_at: string
  updated_at: string
}

export interface VideoJobStep {
  id: number
  stage: VideoJobStage
  attempt: number
  status: 'started' | 'succeeded' | 'failed' | 'skipped'
  provider: string
  started_at: string
  finished_at: string | null
  duration_ms: number | null
  cost_usd: string
  error_code: string | null
  error_detail: string | null
}

export interface VideoListFilters {
  status?: VideoJobStatus
  from?: string
  to?: string
  cursor?: string
}

export type RegenerationStage = 'script' | 'voice' | 'visuals'

export interface RequestChangesPayload {
  reason: string
  regenerate_from: RegenerationStage
}

export interface RejectVideoPayload {
  reason: string
}

export interface UpdateVideoMetadataPayload {
  title?: string
  description?: string
  tags?: string[]
}

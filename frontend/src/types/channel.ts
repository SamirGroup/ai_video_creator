/** Mirrors `youtube_channels` (SPEC 5.3). Token fields never reach the client (C-5). */
export type ChannelStatus = 'connected' | 'disconnected' | 'revoked' | 'error'
export type MonetizationSource = 'api' | 'self_declared' | 'unknown'

export interface YoutubeChannel {
  id: string
  youtube_channel_id: string
  channel_title: string
  channel_handle: string | null
  thumbnail_url: string | null
  subscriber_count: number | null
  video_count: number | null
  is_monetized: boolean | null
  monetization_source: MonetizationSource
  status: ChannelStatus
  last_error_code: string | null
  connected_at: string | null
  last_synced_at: string | null
}

export type AdSenseStatus = 'connected' | 'disconnected' | 'revoked' | 'error'

export interface AdSenseAccount {
  id: string
  adsense_account_id: string
  status: AdSenseStatus
  connected_at: string | null
  last_synced_at: string | null
}

/** Mirrors `content_preferences` (SPEC 5.10). */
export type PublishFrequency = 'daily' | 'weekly' | 'monthly'
export type PrivacyStatus = 'public' | 'unlisted' | 'private'
export type ApprovalMode = 'review_required' | 'auto'

export interface ContentPreferences {
  id: string
  channel_id: string
  niche: string
  custom_brief: string | null
  brand_voice: string | null
  banned_topics: string[]
  language: string
  video_duration_sec: number
  frequency: PublishFrequency
  publish_time_local: string
  publish_timezone: string
  publish_days: number[] | null
  youtube_privacy_status: PrivacyStatus
  youtube_category_id: string
  made_for_kids: boolean
  approval_mode: ApprovalMode
  auto_publish_on_timeout: boolean
  is_paused: boolean
}

export type ContentPreferencesInput = Omit<ContentPreferences, 'id' | 'channel_id'>

export interface RevenueSummary {
  currency: string
  period_start: string
  period_end: string
  total_views: number
  total_estimated_minutes_watched: number
  total_estimated_revenue: string
  total_estimated_ad_revenue: string
  source: 'youtube_analytics' | 'adsense' | 'mixed'
  is_estimated: boolean
}

export interface RevenueDailyPoint {
  date: string
  views: number
  estimated_revenue: string
  is_final: boolean
}

export interface RevenueByVideo {
  job_id: string
  youtube_video_id: string | null
  title: string | null
  views: number
  estimated_revenue: string
  rpm: string | null
}

export type StatementStatus =
  | 'draft'
  | 'finalized'
  | 'invoiced'
  | 'paid'
  | 'disputed'
  | 'written_off'
  | 'carried_forward'

export interface RevenueShareStatement {
  id: string
  period_start: string
  period_end: string
  currency: string
  gross_revenue: string
  platform_share_pct: string
  platform_share_amount: string
  creator_share_amount: string
  video_count: number
  status: StatementStatus
  review_deadline?: string | null
  finalized_at: string | null
  disputed_at: string | null
  dispute_reason: string | null
}

export interface DisputeStatementPayload {
  reason: string
}

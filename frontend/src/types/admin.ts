import type { RoleCode } from './common'
import type { VideoJob } from './video'

export interface AdminUserListItem {
  id: string
  email: string
  full_name: string
  status: 'active' | 'suspended' | 'pending_deletion' | 'deleted'
  roles: RoleCode[]
  plan_code: string | null
  created_at: string
}

export interface AdminUserFilters {
  search?: string
  plan?: string
  status?: string
  cursor?: string
}

export interface AdminVideoJobListItem extends VideoJob {
  user_email: string
}

export interface ModerationQueueItem {
  job_id: string
  stage: 'script' | 'audio' | 'visual' | 'final'
  verdict: 'pass' | 'flag' | 'block'
  categories: Record<string, number>
  created_at: string
  video_title: string | null
  user_email: string
}

export interface ModerationDecisionPayload {
  decision: 'approved' | 'rejected'
  reason: string
}

export interface FinanceOverview {
  mrr: string
  currency: string
  active_subscriptions: number
  revenue_share_total: string
  uncollected_invoices_total: string
  uncollected_invoices_count: number
}

export interface ProviderConfig {
  id: string
  service: 'llm' | 'tts' | 'video_gen' | 'music' | 'moderation' | 'translation' | 'stt'
  provider: string
  display_name: string
  model_name: string | null
  is_primary: boolean
  is_active: boolean
  priority: number
  unit_cost_usd: string | null
  cost_unit: string | null
  rate_limit_per_min: number | null
}

export interface Plan {
  id: string
  code: 'free' | 'starter' | 'professional' | 'enterprise'
  name: string
  price_amount: string
  currency: string
  billing_interval: 'month' | 'six_months'
  videos_per_period: number
  max_video_duration_sec: number
  max_languages: number
  concurrent_jobs: number
  voice_cloning_enabled: boolean
  priority_queue: boolean
  sla_hours: number | null
  is_active: boolean
  sort_order: number
}

export type SubscriptionStatus =
  | 'trialing'
  | 'active'
  | 'past_due'
  | 'suspended'
  | 'canceled'
  | 'expired'

export interface Subscription {
  id: string
  plan: Plan
  status: SubscriptionStatus
  default_payment_method_id: string | null
  current_period_start: string
  current_period_end: string
  cancel_at_period_end: boolean
  grace_period_ends_at: string | null
  revenue_share_paused: boolean
  usage: {
    videos_generated: number
    videos_published: number
    regenerations_used: number
  }
}

export type InvoiceStatus = 'draft' | 'open' | 'paid' | 'failed' | 'void' | 'uncollectible'

export interface Invoice {
  id: string
  kind: 'subscription' | 'revenue_share'
  amount: string
  currency: string
  status: InvoiceStatus
  due_at: string
  paid_at: string | null
  pdf_url: string | null
}

export interface CheckoutSessionResponse {
  checkout_url: string
}

export interface PortalSessionResponse {
  portal_url: string
}

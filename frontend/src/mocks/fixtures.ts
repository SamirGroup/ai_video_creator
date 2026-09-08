/** TODO: real API — fixtures used only until `backend/` exposes real endpoints. */
import type { AdminUserListItem, AdminVideoJobListItem, FinanceOverview, ModerationQueueItem, ProviderConfig } from '@/types/admin'
import type { Invoice, Plan, Subscription } from '@/types/billing'
import type { AdSenseAccount, ContentPreferences, YoutubeChannel } from '@/types/channel'
import type { ContractVersion, SignedContract } from '@/types/contract'
import type { RevenueByVideo, RevenueDailyPoint, RevenueShareStatement, RevenueSummary } from '@/types/revenue'
import type { VideoJob, VideoJobStep } from '@/types/video'

export const mockChannel: YoutubeChannel = {
  id: 'ch_1',
  youtube_channel_id: 'UC1234567890',
  channel_title: 'Wanderlust Explained',
  channel_handle: '@wanderlustexplained',
  thumbnail_url: null,
  subscriber_count: 1830,
  video_count: 42,
  is_monetized: true,
  monetization_source: 'api',
  status: 'connected',
  last_error_code: null,
  connected_at: '2026-06-01T09:00:00Z',
  last_synced_at: '2026-09-06T06:00:00Z',
}

export const mockAdSenseAccount: AdSenseAccount = {
  id: 'ads_1',
  adsense_account_id: 'pub-1234567890123456',
  status: 'connected',
  connected_at: '2026-06-02T10:00:00Z',
  last_synced_at: '2026-09-06T06:00:00Z',
}

export const mockPreferences: ContentPreferences = {
  id: 'pref_1',
  channel_id: 'ch_1',
  niche: 'travel',
  custom_brief: 'Focus on underrated destinations in Central Asia.',
  brand_voice: 'Curious, warm, slightly humorous. Avoid clickbait superlatives.',
  banned_topics: ['politics', 'religion'],
  language: 'en',
  video_duration_sec: 300,
  frequency: 'weekly',
  publish_time_local: '18:00',
  publish_timezone: 'Asia/Tashkent',
  publish_days: [1],
  youtube_privacy_status: 'public',
  youtube_category_id: '19',
  made_for_kids: false,
  approval_mode: 'review_required',
  auto_publish_on_timeout: false,
  is_paused: false,
}

export const mockDashboardSummary = {
  channelConnected: true,
  videosThisMonth: 3,
  videoQuota: 8,
  estimatedRevenueUsd: '186.42',
  pendingApprovals: 1,
}

const now = Date.now()
const iso = (offsetHours: number) => new Date(now + offsetHours * 3600_000).toISOString()

export const mockVideos: VideoJob[] = [
  {
    id: 'job_1',
    channel_id: 'ch_1',
    trigger: 'scheduled',
    status: 'awaiting_approval',
    current_stage: null,
    scheduled_for: iso(2),
    title: '7 Hidden Gems in the Fergana Valley You Have Never Heard Of',
    description: 'A guided tour through underrated spots...',
    tags: ['travel', 'uzbekistan', 'fergana'],
    language: 'en',
    duration_sec: 312,
    thumbnail_s3_key: null,
    preview_url: 'https://example.com/preview/job_1',
    preview_expires_at: iso(24),
    approval_requested_at: iso(-1),
    regeneration_count: 0,
    youtube_video_id: null,
    youtube_url: null,
    published_at: null,
    error_code: null,
    error_message: null,
    total_cost_usd: '4.32',
    created_at: iso(-6),
    updated_at: iso(-1),
  },
  {
    id: 'job_2',
    channel_id: 'ch_1',
    trigger: 'scheduled',
    status: 'published',
    current_stage: null,
    scheduled_for: iso(-24),
    title: 'A Day in Khiva: Walking the Ancient Silk Road City',
    description: null,
    tags: ['travel', 'khiva'],
    language: 'en',
    duration_sec: 298,
    thumbnail_s3_key: null,
    preview_url: null,
    preview_expires_at: null,
    approval_requested_at: iso(-30),
    regeneration_count: 0,
    youtube_video_id: 'dQw4w9WgXcQ',
    youtube_url: 'https://youtube.com/watch?v=dQw4w9WgXcQ',
    published_at: iso(-26),
    error_code: null,
    error_message: null,
    total_cost_usd: '3.98',
    created_at: iso(-36),
    updated_at: iso(-26),
  },
  {
    id: 'job_3',
    channel_id: 'ch_1',
    trigger: 'scheduled',
    status: 'generating_visuals',
    current_stage: 'visuals',
    scheduled_for: iso(48),
    title: null,
    description: null,
    tags: [],
    language: 'en',
    duration_sec: null,
    thumbnail_s3_key: null,
    preview_url: null,
    preview_expires_at: null,
    approval_requested_at: null,
    regeneration_count: 0,
    youtube_video_id: null,
    youtube_url: null,
    published_at: null,
    error_code: null,
    error_message: null,
    total_cost_usd: '1.75',
    created_at: iso(-1),
    updated_at: iso(0),
  },
  {
    id: 'job_4',
    channel_id: 'ch_1',
    trigger: 'manual',
    status: 'failed',
    current_stage: 'voice',
    scheduled_for: iso(-3),
    title: 'Samarkand at Sunset',
    description: null,
    tags: [],
    language: 'en',
    duration_sec: null,
    thumbnail_s3_key: null,
    preview_url: null,
    preview_expires_at: null,
    approval_requested_at: null,
    regeneration_count: 1,
    youtube_video_id: null,
    youtube_url: null,
    published_at: null,
    error_code: 'tts_provider_timeout',
    error_message: 'ElevenLabs did not respond within the retry window.',
    total_cost_usd: '0.61',
    created_at: iso(-5),
    updated_at: iso(-3),
  },
  {
    id: 'job_5',
    channel_id: 'ch_1',
    trigger: 'scheduled',
    status: 'moderation_review',
    current_stage: null,
    scheduled_for: iso(6),
    title: 'Street Food Tour: Tashkent Night Market',
    description: null,
    tags: ['food', 'tashkent'],
    language: 'en',
    duration_sec: 280,
    thumbnail_s3_key: null,
    preview_url: null,
    preview_expires_at: null,
    approval_requested_at: null,
    regeneration_count: 0,
    youtube_video_id: null,
    youtube_url: null,
    published_at: null,
    error_code: null,
    error_message: null,
    total_cost_usd: '3.10',
    created_at: iso(-2),
    updated_at: iso(0),
  },
]

export const mockVideoSteps: Record<string, VideoJobStep[]> = {
  job_1: [
    { id: 1, stage: 'script', attempt: 1, status: 'succeeded', provider: 'openrouter', started_at: iso(-6), finished_at: iso(-5.8), duration_ms: 720000, cost_usd: '0.42', error_code: null, error_detail: null },
    { id: 2, stage: 'voice', attempt: 1, status: 'succeeded', provider: 'elevenlabs', started_at: iso(-5.8), finished_at: iso(-5.5), duration_ms: 1080000, cost_usd: '0.88', error_code: null, error_detail: null },
    { id: 3, stage: 'visuals', attempt: 1, status: 'succeeded', provider: 'runway', started_at: iso(-5.5), finished_at: iso(-2), duration_ms: 12600000, cost_usd: '2.60', error_code: null, error_detail: null },
    { id: 4, stage: 'assembly', attempt: 1, status: 'succeeded', provider: 'ffmpeg', started_at: iso(-2), finished_at: iso(-1.5), duration_ms: 1800000, cost_usd: '0.42', error_code: null, error_detail: null },
    { id: 5, stage: 'moderation', attempt: 1, status: 'succeeded', provider: 'aws_rekognition', started_at: iso(-1.5), finished_at: iso(-1), duration_ms: 300000, cost_usd: '0.00', error_code: null, error_detail: null },
  ],
}

export const mockRevenueSummary: RevenueSummary = {
  currency: 'USD',
  period_start: '2026-08-01',
  period_end: '2026-08-31',
  total_views: 48210,
  total_estimated_minutes_watched: 96420,
  total_estimated_revenue: '186.42',
  total_estimated_ad_revenue: '186.42',
  source: 'adsense',
  is_estimated: false,
}

export const mockRevenueDaily: RevenueDailyPoint[] = Array.from({ length: 14 }).map((_, i) => ({
  date: new Date(now - (13 - i) * 86400_000).toISOString().slice(0, 10),
  views: Math.round(1200 + Math.sin(i / 2) * 400 + i * 30),
  estimated_revenue: (4 + Math.sin(i / 3) * 2 + i * 0.2).toFixed(2),
  is_final: i < 10,
}))

export const mockRevenueByVideo: RevenueByVideo[] = [
  { job_id: 'job_2', youtube_video_id: 'dQw4w9WgXcQ', title: 'A Day in Khiva: Walking the Ancient Silk Road City', views: 12840, estimated_revenue: '58.10', rpm: '4.52' },
  { job_id: 'job_old_1', youtube_video_id: 'abc123', title: 'Bukhara in 48 Hours', views: 9720, estimated_revenue: '41.30', rpm: '4.25' },
  { job_id: 'job_old_2', youtube_video_id: 'def456', title: 'Is Nukus Worth Visiting?', views: 6110, estimated_revenue: '22.87', rpm: '3.74' },
]

export const mockStatements: RevenueShareStatement[] = [
  {
    id: 'stmt_2026_08',
    period_start: '2026-08-01',
    period_end: '2026-08-31',
    currency: 'USD',
    gross_revenue: '186.42',
    platform_share_pct: '50.00',
    platform_share_amount: '93.21',
    creator_share_amount: '93.21',
    video_count: 6,
    status: 'invoiced',
    finalized_at: '2026-09-10T00:00:00Z',
    disputed_at: null,
    dispute_reason: null,
  },
  {
    id: 'stmt_2026_07',
    period_start: '2026-07-01',
    period_end: '2026-07-31',
    currency: 'USD',
    gross_revenue: '142.05',
    platform_share_pct: '50.00',
    platform_share_amount: '71.03',
    creator_share_amount: '71.02',
    video_count: 5,
    status: 'paid',
    finalized_at: '2026-08-10T00:00:00Z',
    disputed_at: null,
    dispute_reason: null,
  },
]

export const mockPlans: Plan[] = [
  { id: 'plan_free', code: 'free', name: 'Free', price_amount: '0', currency: 'USD', billing_interval: 'month', videos_per_period: 2, max_video_duration_sec: 60, max_languages: 1, concurrent_jobs: 1, voice_cloning_enabled: false, priority_queue: false, sla_hours: null, is_active: true, sort_order: 0 },
  { id: 'plan_starter', code: 'starter', name: 'Starter', price_amount: '50', currency: 'USD', billing_interval: 'month', videos_per_period: 8, max_video_duration_sec: 300, max_languages: 1, concurrent_jobs: 1, voice_cloning_enabled: false, priority_queue: false, sla_hours: null, is_active: true, sort_order: 1 },
  { id: 'plan_pro', code: 'professional', name: 'Professional', price_amount: '100', currency: 'USD', billing_interval: 'month', videos_per_period: 20, max_video_duration_sec: 600, max_languages: 1, concurrent_jobs: 2, voice_cloning_enabled: true, priority_queue: true, sla_hours: null, is_active: true, sort_order: 2 },
  { id: 'plan_ent', code: 'enterprise', name: 'Enterprise', price_amount: '599', currency: 'USD', billing_interval: 'six_months', videos_per_period: 60, max_video_duration_sec: 600, max_languages: 1, concurrent_jobs: 5, voice_cloning_enabled: true, priority_queue: true, sla_hours: 24, is_active: true, sort_order: 3 },
]

export const mockSubscription: Subscription = {
  id: 'sub_1',
  plan: mockPlans[1],
  status: 'active',
  default_payment_method_id: 'pm_mock_123',
  current_period_start: '2026-08-15T00:00:00Z',
  current_period_end: '2026-09-15T00:00:00Z',
  cancel_at_period_end: false,
  grace_period_ends_at: null,
  revenue_share_paused: false,
  usage: { videos_generated: 3, videos_published: 2, regenerations_used: 1 },
}

export const mockInvoices: Invoice[] = [
  { id: 'inv_1', kind: 'subscription', amount: '50.00', currency: 'USD', status: 'paid', due_at: '2026-08-15T00:00:00Z', paid_at: '2026-08-15T00:04:00Z', pdf_url: '#' },
  { id: 'inv_2', kind: 'revenue_share', amount: '71.03', currency: 'USD', status: 'paid', due_at: '2026-08-10T00:00:00Z', paid_at: '2026-08-10T02:00:00Z', pdf_url: '#' },
  { id: 'inv_3', kind: 'revenue_share', amount: '93.21', currency: 'USD', status: 'open', due_at: '2026-09-10T00:00:00Z', paid_at: null, pdf_url: null },
]

export const mockContractVersion: ContractVersion = {
  id: 'cv_3',
  version: '1.3',
  title: 'AI Production & Revenue-Share Service Agreement',
  body_markdown:
    '## 1. Revenue share\nThe Platform invoices the Creator 50% of gross ad revenue generated by Platform-produced videos as an AI production & revenue-share service fee...\n\n## 2. Publishing rights\nThe Creator grants the Platform permission to publish AI-generated videos to the connected YouTube channel...',
  revenue_share_platform_pct: '50.00',
  revenue_share_creator_pct: '50.00',
  effective_from: '2026-07-01T00:00:00Z',
}

export const mockSignedContracts: SignedContract[] = [
  { id: 'c_1', contract_version_id: 'cv_3', version: '1.3', signed_at: '2026-07-02T14:30:00Z', status: 'active', pdf_url: '#' },
]

// ---- Admin fixtures ----

export const mockAdminUsers: AdminUserListItem[] = [
  { id: 'u_1', email: 'amira@example.com', full_name: 'Amira K.', status: 'active', roles: ['creator'], plan_code: 'professional', created_at: '2026-05-12T00:00:00Z' },
  { id: 'u_2', email: 'jasur@example.com', full_name: 'Jasur T.', status: 'suspended', roles: ['creator'], plan_code: 'starter', created_at: '2026-04-02T00:00:00Z' },
  { id: 'u_3', email: 'dina@example.com', full_name: 'Dina R.', status: 'active', roles: ['creator'], plan_code: 'free', created_at: '2026-08-20T00:00:00Z' },
  { id: 'u_4', email: 'ops@ai-youtuber.com', full_name: 'Ops Admin', status: 'active', roles: ['admin', 'finance'], plan_code: null, created_at: '2026-01-01T00:00:00Z' },
]

export const mockAdminVideos: AdminVideoJobListItem[] = mockVideos.map((v) => ({
  ...v,
  user_email: 'amira@example.com',
}))

export const mockModerationQueue: ModerationQueueItem[] = [
  { job_id: 'job_5', stage: 'final', verdict: 'flag', categories: { violence: 0.12, hate: 0.02, sexual: 0.31 }, created_at: iso(-1), video_title: 'Street Food Tour: Tashkent Night Market', user_email: 'amira@example.com' },
]

export const mockFinanceOverview: FinanceOverview = {
  mrr: '4280.00',
  currency: 'USD',
  active_subscriptions: 62,
  revenue_share_total: '3140.55',
  uncollected_invoices_total: '412.00',
  uncollected_invoices_count: 5,
}

export const mockProviders: ProviderConfig[] = [
  { id: 'p_1', service: 'llm', provider: 'openrouter', display_name: 'OpenRouter (Claude 4.5)', model_name: 'anthropic/claude-4.5-sonnet', is_primary: true, is_active: true, priority: 1, unit_cost_usd: '0.000015', cost_unit: 'per_1k_tokens', rate_limit_per_min: 60 },
  { id: 'p_2', service: 'tts', provider: 'elevenlabs', display_name: 'ElevenLabs', model_name: 'eleven_multilingual_v2', is_primary: true, is_active: true, priority: 1, unit_cost_usd: '0.00003', cost_unit: 'per_char', rate_limit_per_min: 30 },
  { id: 'p_3', service: 'video_gen', provider: 'runway', display_name: 'Runway Gen-4', model_name: 'gen4_turbo', is_primary: true, is_active: true, priority: 1, unit_cost_usd: '0.25', cost_unit: 'per_clip', rate_limit_per_min: 10 },
  { id: 'p_4', service: 'moderation', provider: 'openai_moderation', display_name: 'OpenAI Moderation', model_name: 'omni-moderation-latest', is_primary: true, is_active: true, priority: 1, unit_cost_usd: null, cost_unit: null, rate_limit_per_min: 300 },
]

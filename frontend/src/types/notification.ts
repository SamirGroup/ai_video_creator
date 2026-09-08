export interface NotificationItem {
  id: string
  type: string
  title: string
  body: string
  related_job_id: string | null
  status: 'queued' | 'sent' | 'failed' | 'read'
  read_at: string | null
  created_at: string
}

export interface NotificationPreference {
  type: string
  email_enabled: boolean
  in_app_enabled: boolean
  push_enabled: boolean
}

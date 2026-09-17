export interface ContractVersion {
  id: string
  version: string
  title: string
  body_markdown: string
  revenue_share_platform_pct: string
  revenue_share_creator_pct: string
  effective_from: string
}

export type ContractStatus = 'active' | 'superseded' | 'terminated'

export interface SignedContract {
  id: string
  contract_version_id: string
  version: string
  signed_at: string
  status: ContractStatus
  pdf_url: string | null
}

/** Granular consent checkboxes required at sign time (FR-30). */
export interface SignContractPayload {
  contract_version_id: string
  consent_revenue_share: boolean
  consent_publish_to_channel: boolean
  consent_data_processing: boolean
  consent_marketing: boolean
  /** Stripe SetupIntent id confirming a saved payment method (FR-70a). */
  setup_intent_id?: string
}

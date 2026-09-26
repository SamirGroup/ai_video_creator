import { apiClient } from './client'

export type ContractType = 'resident' | 'non_resident'

export interface ServicePackage {
  id: string
  code: string
  price_usd: string
  /** Set for a range such as 1–2 hours; otherwise delivery is within `delivery_hours`. */
  delivery_hours_min: number | null
  delivery_hours: number
  revision_rounds: number
  support_months: number
  /** 0 means the page count comes from the technical specification. */
  page_limit: number
  languages: number
  sort_order?: number
  is_active?: boolean
}

export interface ServiceCatalog {
  sales_ready: boolean
  reason: string
  currency: string
  packages: ServicePackage[]
}

export interface CustomerDetails {
  full_name: string
  date_of_birth: string
  passport_number: string
  passport_issued_by: string
  passport_issued_at: string
  address: string
  city: string
  phone: string
  email: string
  pinfl?: string
  citizenship?: string
  citizenship_code?: string
  country?: string
  country_code?: string
  tax_id?: string
}

export interface ProjectBrief {
  name: string
  description: string
  reference_url?: string
}

export type Clause = string | { text: string; items: string[] }

export interface ContractDocument {
  version: string
  type: ContractType
  language: 'uz' | 'en'
  number: string
  date: string
  city: string
  title: string
  preamble: string
  price: string
  currency: string
  package_name: string
  sections: { title: string; clauses: Clause[] }[]
  annex_title: string
  annex_rows: [string, string][]
  annex_label: string
  annex_description: string
  executor_rows: [string, string][]
  customer_rows: [string, string][]
  executor_signatory: string
  customer_signatory: string
  labels: Record<string, string>
  acceptance?: { accepted_at: string; ip: string | null; checksum: string }
}

export interface ServiceOrder {
  id: string
  number: string
  package: string
  price_usd: string
  currency: string
  contract_type: ContractType
  project_name: string
  status: string
  checkout_url: string
  paid_at: string | null
  accepted_at: string
  created_at: string
  user_email?: string
  account_label?: string
  charge_id?: string
  admin_note?: string
  contract_sha256?: string
  contract?: ContractDocument
}

export interface ExecutorProfile {
  legal_name: string
  director_name: string
  acting_basis: string
  acting_basis_en: string
  address: string
  city: string
  city_en: string
  tin: string
  bank_name: string
  bank_account: string
  bank_code: string
  swift: string
  phone: string
  email: string
  vat_note: string
  sales_enabled: boolean
  complete?: boolean
  sales_ready?: boolean
  reason?: string
}

interface Draft {
  package: string
  contract_type: ContractType
  customer: CustomerDetails
  project: ProjectBrief
}

export const webServicesApi = {
  catalog: async () => (await apiClient.get<ServiceCatalog>('/public/web-services')).data,
  preview: async (draft: Draft) =>
    (
      await apiClient.post<{ document: ContractDocument; checksum: string }>(
        '/web-services/contract-preview',
        draft,
      )
    ).data,
  orders: async () => (await apiClient.get<ServiceOrder[]>('/web-services/orders')).data,
  order: async (id: string) =>
    (await apiClient.get<ServiceOrder>(`/web-services/orders/${id}`)).data,
  place: async (
    draft: Draft & {
      request_key: string
      quoted_total: string
      preview_checksum: string
      accept_terms: boolean
    },
  ) => (await apiClient.post<ServiceOrder>('/web-services/orders', draft)).data,
  pay: async (id: string) =>
    (await apiClient.post<ServiceOrder>(`/web-services/orders/${id}/pay`)).data,
  confirm: async (id: string) =>
    (await apiClient.post<ServiceOrder>(`/web-services/orders/${id}/confirm`)).data,
}

const admin = '/admin/web-services'
export const adminWebServicesApi = {
  executor: async () => (await apiClient.get<ExecutorProfile>(`${admin}/executor`)).data,
  saveExecutor: async (profile: Partial<ExecutorProfile>) =>
    (await apiClient.put<ExecutorProfile>(`${admin}/executor`, profile)).data,
  packages: async () => (await apiClient.get<ServicePackage[]>(`${admin}/packages`)).data,
  savePackage: async (id: string, patch: Partial<ServicePackage>) =>
    (await apiClient.patch<ServicePackage>(`${admin}/packages/${id}`, patch)).data,
  orders: async () => (await apiClient.get<ServiceOrder[]>(`${admin}/orders`)).data,
  order: async (id: string) =>
    (await apiClient.get<ServiceOrder>(`${admin}/orders/${id}`)).data,
  setStatus: async (id: string, status: string, admin_note?: string) =>
    (await apiClient.patch<ServiceOrder>(`${admin}/orders/${id}`, { status, admin_note }))
      .data,
  refund: async (id: string) =>
    (await apiClient.post<ServiceOrder>(`${admin}/orders/${id}/refund`)).data,
  confirm: async (id: string) =>
    (await apiClient.post<ServiceOrder>(`${admin}/orders/${id}/confirm`)).data,
}

import { apiClient } from './client'

export interface PayoneerAccount {
  id: string
  label: string
  environment: 'sandbox' | 'live'
  is_active: boolean
  checkout_enabled: boolean
  is_default_checkout: boolean
  merchant_code: string
  division: string
  payment_token_set: boolean
  payouts_enabled: boolean
  is_default_payouts: boolean
  program_id: string
  client_id: string
  client_secret_set: boolean
  checkout_ready: boolean
  payouts_ready: boolean
  notification_url: string
  last_checked_at: string | null
  last_check_ok: boolean | null
  last_check_detail: string
}

/** Write shape: secrets are sent only when typed, never read back. */
export type PayoneerAccountInput = Partial<
  Omit<PayoneerAccount, 'id' | 'payment_token_set' | 'client_secret_set'>
> & { payment_token?: string; client_secret?: string }

export interface PayoneerPayee {
  id: string
  account: string
  account_label: string
  user_email: string
  display_name: string
  email: string
  payee_id: string
  status: 'invited' | 'active' | 'inactive'
  provider_status: string
  last_checked_at: string | null
}

export interface PayoneerPayout {
  id: string
  account_label: string
  payee: string
  payee_name: string
  amount: string
  currency: string
  description: string
  client_reference_id: string
  status: 'submitting' | 'pending' | 'transferred' | 'failed' | 'canceled'
  provider_status: string
  payout_id: string
  reason: string
  submitted_at: string | null
  created_at: string
}

const root = '/admin/payoneer'
export const payoneerApi = {
  accounts: async () => (await apiClient.get<PayoneerAccount[]>(`${root}/accounts`)).data,
  saveAccount: async (input: PayoneerAccountInput, id?: string) =>
    (id
      ? await apiClient.patch<PayoneerAccount>(`${root}/accounts/${id}`, input)
      : await apiClient.post<PayoneerAccount>(`${root}/accounts`, input)
    ).data,
  removeAccount: async (id: string) => apiClient.delete(`${root}/accounts/${id}`),
  checkAccount: async (id: string) =>
    (await apiClient.post<PayoneerAccount>(`${root}/accounts/${id}/check`)).data,
  payees: async () => (await apiClient.get<PayoneerPayee[]>(`${root}/payees`)).data,
  addPayee: async (input: { account: string; display_name: string; email: string }) =>
    (await apiClient.post<PayoneerPayee>(`${root}/payees`, input)).data,
  invitePayee: async (id: string) =>
    (await apiClient.post<{ registration_link: string }>(`${root}/payees/${id}/invite`))
      .data,
  refreshPayee: async (id: string) =>
    (await apiClient.post<PayoneerPayee>(`${root}/payees/${id}/refresh`)).data,
  payouts: async () => (await apiClient.get<PayoneerPayout[]>(`${root}/payouts`)).data,
  createPayout: async (input: { payee: string; amount: string; description: string }) =>
    (await apiClient.post<PayoneerPayout>(`${root}/payouts`, input)).data,
  submitPayout: async (id: string) =>
    (await apiClient.post<PayoneerPayout>(`${root}/payouts/${id}/submit`)).data,
  refreshPayout: async (id: string) =>
    (await apiClient.post<PayoneerPayout>(`${root}/payouts/${id}/refresh`)).data,
}

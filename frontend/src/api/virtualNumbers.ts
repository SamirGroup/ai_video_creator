import { apiClient } from './client'
export interface NumberPrice {
  base_cost: string
  profit_pct: string
  profit: string
  tax_pct: string
  tax: string
  tax_basis: 'base' | 'subtotal'
  tax_base: string
  subtotal: string
  total: string
  currency: string
  version: string
}
export interface NumberPaymentMethod {
  code: string
  label: string
  available: boolean
  mode: string
  reason: string
}

export interface NumberOffer {
  id: string
  name: string
  country_code: string
  country_name: string
  service: string
  number_type: string
  provider: string
  price_usd: string
  price_breakdown?: NumberPrice | null
  base_cost_usd?: string
  tax_basis?: 'base' | 'subtotal'
  rental_days: number
  description: string
  unavailable_reason: string
  available_count: number
  is_visible?: boolean
  sales_enabled?: boolean
  contract_confirmed?: boolean
  compatibility_confirmed?: boolean
}
export interface NumberOrder {
  id: string
  offer_name: string
  service: string
  price_usd: string
  price_breakdown?: NumberPrice | null
  payment_provider?: string
  rental_days: number
  status: string
  number: string | null
  checkout_url: string
  activated_at: string | null
  expires_at: string | null
  created_at: string
  refund_reason: string
  user_id?: string
}
export interface SMS {
  id: string
  sender: string
  body: string
  received_at: string
}
const root = '/virtual-numbers'
const admin = '/admin/virtual-numbers'
export const virtualNumbersApi = {
  catalog: async () =>
    (
      await apiClient.get<{
        sales_ready: boolean
        offers: NumberOffer[]
        payment_methods: NumberPaymentMethod[]
      }>(`${root}/catalog`)
    ).data,
  orders: async () => (await apiClient.get<NumberOrder[]>(`${root}/orders`)).data,
  purchase: async (
    offer_id: string,
    request_key: string,
    payment_provider: string,
    quoted_total: string,
  ) =>
    (
      await apiClient.post<NumberOrder>(`${root}/orders`, {
        offer_id,
        request_key,
        payment_provider,
        quoted_total,
        terms_accepted: true,
      })
    ).data,
  capturePayPal: async (id: string) =>
    (await apiClient.post<NumberOrder>(`${root}/orders/${id}/paypal-capture`)).data,
  paymentReadiness: async () =>
    (
      await apiClient.get<{
        sales_ready: boolean
        payment_methods: NumberPaymentMethod[]
        allpay_requirements: string[]
      }>(`${admin}/payments`)
    ).data,
  previewPrice: async (base_cost_usd: string, tax_basis: string) =>
    (
      await apiClient.get<NumberPrice>(`${admin}/price-preview`, {
        params: { base_cost_usd, tax_basis },
      })
    ).data,
  messages: async (id: string) =>
    (await apiClient.get<SMS[]>(`${root}/orders/${id}/messages`)).data,
  requestRefund: async (id: string, reason: string) =>
    apiClient.post(`${root}/orders/${id}/refund`, { reason }),
  offers: async () => (await apiClient.get<NumberOffer[]>(`${admin}/offers`)).data,
  saveOffer: async (data: Partial<NumberOffer>, id?: string) =>
    id
      ? apiClient.patch(`${admin}/offers/${id}`, data)
      : apiClient.post(`${admin}/offers`, data),
  addNumber: async (data: {
    offer: string
    number: string
    provider_reference: string
  }) => apiClient.post(`${admin}/inventory`, data),
  adminOrders: async () => (await apiClient.get<NumberOrder[]>(`${admin}/orders`)).data,
  refund: async (id: string) => apiClient.post(`${admin}/orders/${id}/refund`),
}

export const numberStatus: Record<string, string> = {
  pending: 'To‘lov kutilmoqda',
  active: 'Faol',
  expired: 'Muddati tugagan',
  canceled: 'Bekor qilingan',
  refund_requested: 'Qaytarish so‘rovi ko‘rilmoqda',
  refunded: 'Pul qaytarilgan',
}

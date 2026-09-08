import { apiClient } from './client'
import type {
  CheckoutSessionResponse,
  Invoice,
  Plan,
  PortalSessionResponse,
  Subscription,
} from '@/types/billing'

// Endpoint group: Plans & Billing (SPEC 6, FR-21..FR-27). TODO: real API.
export const billingApi = {
  listPlans: () => apiClient.get<Plan[]>('/plans').then((r) => r.data),

  mySubscription: () =>
    apiClient.get<Subscription>('/me/subscription').then((r) => r.data),

  createCheckoutSession: (planCode: string) =>
    apiClient
      .post<CheckoutSessionResponse>('/billing/checkout-session', { plan_code: planCode })
      .then((r) => r.data),

  createPortalSession: () =>
    apiClient.post<PortalSessionResponse>('/billing/portal-session').then((r) => r.data),

  listInvoices: () => apiClient.get<Invoice[]>('/invoices').then((r) => r.data),

  invoicePdfUrl: (id: string) => `/api/v1/invoices/${id}/pdf`,
}

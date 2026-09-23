// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { virtualNumbersApi as api } from '@/api/virtualNumbers'
import i18n from '@/i18n'
import { VirtualNumbersPage } from './VirtualNumbersPage'
vi.mock('@/api/virtualNumbers', () => ({ numberStatus: {}, virtualNumbersApi: { catalog: vi.fn(), orders: vi.fn(), purchase: vi.fn(), messages: vi.fn(), requestRefund: vi.fn(), capturePayPal: vi.fn() } }))
const offer = { id: 'offer1', name: 'UK mobile', country_code: 'GB', country_name: 'UK', service: 'telegram', number_type: 'mobile', provider: 'Test', price_usd: '5.00', rental_days: 30, description: '', available_count: 1, unavailable_reason: '' }
beforeEach(async () => { vi.resetAllMocks(); await i18n.changeLanguage('en'); vi.mocked(api.orders).mockResolvedValue([]) })
afterEach(cleanup)
function mount() { render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}><VirtualNumbersPage /></QueryClientProvider>) }
it('does not allow payment before launch even after consent', async () => {
  vi.mocked(api.catalog).mockResolvedValue({ sales_ready: false, payment_methods: [{ code: 'stripe', label: 'Visa / Stripe', available: false, mode: 'test', reason: 'credentials_required' }], offers: [{ ...offer, unavailable_reason: 'integration_pending' }] })
  mount()
  const button = await screen.findByRole('button', { name: 'Rent' })
  fireEvent.click(screen.getByRole('checkbox'))
  expect((button as HTMLButtonElement).disabled).toBe(true)
  fireEvent.click(button)
  expect(api.purchase).not.toHaveBeenCalled()
})
it('requires consent and reuses request key after a network failure', async () => {
  vi.mocked(api.catalog).mockResolvedValue({ sales_ready: true, payment_methods: [{ code: 'stripe', label: 'Visa / Stripe', available: true, mode: 'test', reason: '' }], offers: [offer] })
  vi.mocked(api.purchase).mockRejectedValue(new Error('Temporary failure'))
  mount()
  const button = await screen.findByRole('button', { name: 'Rent' })
  expect((button as HTMLButtonElement).disabled).toBe(true)
  fireEvent.click(screen.getByRole('checkbox'))
  fireEvent.click(button)
  await screen.findByText('Temporary failure')
  fireEvent.click(button)
  await waitFor(() => expect(api.purchase).toHaveBeenCalledTimes(2))
  expect(vi.mocked(api.purchase).mock.calls[0]).toEqual(vi.mocked(api.purchase).mock.calls[1])
})

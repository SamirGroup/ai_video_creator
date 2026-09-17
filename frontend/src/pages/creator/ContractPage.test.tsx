// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { contractsApi } from '@/api/contracts'
import i18n from '@/i18n'
import { ContractPage } from './ContractPage'

vi.mock('@/api/contracts', () => ({
  contractsApi: {
    current: vi.fn(),
    history: vi.fn(),
    sign: vi.fn(),
    downloadPdf: vi.fn(),
  },
}))
const state = {
  version: {
    id: 'version-30',
    version: '2.0',
    title: 'Creator agreement',
    body_markdown: '30% platform / 70% creator',
    revenue_share_platform_pct: '30.00',
    revenue_share_creator_pct: '70.00',
    effective_from: '2026-09-17T00:00:00Z',
  },
  signed: false,
  has_payment_method: true,
  requires_signature: true,
  requires_resign: false,
  generation_allowed: false,
  generation_block_code: 'CONTRACT_REQUIRED',
}
beforeEach(async () => {
  vi.resetAllMocks()
  await i18n.changeLanguage('en')
  vi.mocked(contractsApi.current).mockResolvedValue(state)
  vi.mocked(contractsApi.history).mockResolvedValue([])
})
afterEach(cleanup)
function mount() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  render(
    <QueryClientProvider client={client}>
      <ContractPage />
    </QueryClientProvider>,
  )
}
it('shows server percentages and submits only explicitly checked consent', async () => {
  vi.mocked(contractsApi.sign).mockResolvedValue({
    id: 'signed',
    contract_version_id: 'version-30',
    version: '2.0',
    signed_at: '2026-09-17',
    status: 'active',
    pdf_url: null,
  })
  mount()
  const consent = await screen.findByLabelText(
    'I agree to a 30.00% platform share and 70.00% creator share only on revenue from videos created inside the ecosystem and published through it. Revenue from other videos is excluded.',
  )
  expect((consent as HTMLInputElement).checked).toBe(false)
  const boxes = screen.getAllByRole('checkbox')
  for (const box of boxes.slice(0, 3)) fireEvent.click(box)
  fireEvent.click(screen.getByRole('button', { name: 'Sign contract' }))
  await waitFor(() =>
    expect(contractsApi.sign).toHaveBeenCalledWith({
      contract_version_id: 'version-30',
      consent_revenue_share: true,
      consent_publish_to_channel: true,
      consent_data_processing: true,
      consent_marketing: false,
    }),
  )
})
it('shows historical 50/50 accurately instead of relabeling existing terms', async () => {
  vi.mocked(contractsApi.current).mockResolvedValue({
    ...state,
    version: {
      ...state.version,
      revenue_share_platform_pct: '50.00',
      revenue_share_creator_pct: '50.00',
    },
  })
  mount()
  await screen.findByLabelText(
    'I agree to a 50.00% platform share and 50.00% creator share only on revenue from videos created inside the ecosystem and published through it. Revenue from other videos is excluded.',
  )
  expect(contractsApi.sign).not.toHaveBeenCalled()
})

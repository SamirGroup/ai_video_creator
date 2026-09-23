import { createElement, useEffect } from 'react'

/** Shared public banner used by both the React landing and standalone landing. */
export function PartnersBanner() {
  useEffect(() => {
    if (
      customElements.get('creator-partners') ||
      document.querySelector('script[data-partners-banner]')
    )
      return
    const script = document.createElement('script')
    script.src = '/mw/partners.js?v=1'
    script.dataset.partnersBanner = 'true'
    script.defer = true
    document.head.append(script)
  }, [])
  return createElement('creator-partners')
}

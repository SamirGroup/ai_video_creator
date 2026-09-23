import { Component, type ErrorInfo, type ReactNode } from 'react'

import { Button } from '@/components/ui/Button'
import i18n from '@/i18n'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
}

/**
 * Top-level render-error safety net. TODO: forward `error`/`errorInfo` to
 * Sentry once `VITE_SENTRY_DSN` is wired (NFR-30) — never log PII/tokens.
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false }

  static getDerivedStateFromError(): State {
    return { hasError: true }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Unhandled render error', error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex min-h-svh flex-col items-center justify-center gap-4 bg-background p-6 text-center text-foreground">
          <h1 className="text-lg font-semibold">{i18n.t('common.error.title')}</h1>
          <p className="max-w-sm text-sm text-muted-foreground">
            {i18n.t('common.crashDescription')}
          </p>
          <Button onClick={() => window.location.reload()}>
            {i18n.t('common.reload')}
          </Button>
        </div>
      )
    }
    return this.props.children
  }
}

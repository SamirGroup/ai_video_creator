import { useTranslation } from 'react-i18next'

import { cn } from '@/lib/cn'

const LOCALES = [
  { code: 'en', label: 'EN' },
  { code: 'ru', label: 'RU' },
  { code: 'uz', label: "O'Z" },
] as const

export function LanguageSwitcher() {
  const { i18n, t } = useTranslation()

  return (
    <div
      role="group"
      aria-label={t('nav.language')}
      className="flex items-center gap-0.5 rounded-md border border-border p-0.5"
    >
      {LOCALES.map((locale) => {
        const isActive = i18n.resolvedLanguage === locale.code
        return (
          <button
            key={locale.code}
            type="button"
            aria-pressed={isActive}
            onClick={() => void i18n.changeLanguage(locale.code)}
            className={cn(
              'rounded px-2 py-1 text-xs font-medium transition-colors',
              'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
              isActive
                ? 'bg-primary-600 text-white'
                : 'text-muted-foreground hover:bg-muted',
            )}
          >
            {locale.label}
          </button>
        )
      })}
    </div>
  )
}

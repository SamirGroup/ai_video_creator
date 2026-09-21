import { useTranslation } from 'react-i18next'
import { LANGUAGES } from '@/i18n/registry'
// Selecting a locale fetches its chunk before switching (see i18n/index.ts).
import { changeLocale } from '@/i18n'

export function LanguageSwitcher() {
  const { i18n, t } = useTranslation()
  return (
    <select
      aria-label={t('nav.language')}
      value={i18n.language}
      onChange={(event) => void changeLocale(event.target.value)}
      className="max-w-40 rounded-md border border-border bg-surface px-2 py-1 text-sm text-foreground"
    >
      {LANGUAGES.map((language) => (
        <option key={language.code} value={language.code} lang={language.code}>
          {language.native_name}
        </option>
      ))}
    </select>
  )
}

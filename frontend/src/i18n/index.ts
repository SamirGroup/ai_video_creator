import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import { DEFAULT_LOCALE, SUPPORTED_LOCALES, directionFor } from './registry'

export { SUPPORTED_LOCALES } from './registry'
const modules = import.meta.glob<{ default: Record<string, unknown> }>(
  './locales/*.json',
  { eager: true },
)
const resources = Object.fromEntries(
  SUPPORTED_LOCALES.map((code) => [
    code,
    {
      translation: modules[`./locales/${code}.json`].default,
    },
  ]),
)
let selected = DEFAULT_LOCALE
try {
  const stored = localStorage.getItem('ai-youtuber-locale')
  if (stored && SUPPORTED_LOCALES.includes(stored)) selected = stored
} catch {
  /* Storage can be disabled; keep the Russian default. */
}

export function applyDocumentLocale(locale: string) {
  if (typeof document !== 'undefined') {
    document.documentElement.lang = locale
    document.documentElement.dir = directionFor(locale)
  }
  try {
    localStorage.setItem('ai-youtuber-locale', locale)
  } catch {
    /* Optional persistence. */
  }
}

i18n.on('languageChanged', applyDocumentLocale)
void i18n.use(initReactI18next).init({
  resources,
  lng: selected,
  fallbackLng: DEFAULT_LOCALE,
  supportedLngs: SUPPORTED_LOCALES,
  load: 'currentOnly',
  interpolation: { escapeValue: false },
})
applyDocumentLocale(selected)
export default i18n

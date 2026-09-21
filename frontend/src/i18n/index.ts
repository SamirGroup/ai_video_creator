import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import { DEFAULT_LOCALE, SUPPORTED_LOCALES, directionFor } from './registry'

import ru from './locales/ru.json'
import en from './locales/en.json'
import uz from './locales/uz.json'

export { SUPPORTED_LOCALES } from './registry'

/* All 30 locales are complete, which is ~400 kB of JSON. Bundling them eagerly
   put every one of them in the entry chunk, so a visitor who only ever reads
   the landing page in one language still downloaded the other 29.

   The three locales the product is actually authored in are bundled up front
   so the first paint never waits on a fetch; the rest are code-split by Vite
   and pulled in only when someone selects them. */
const CORE = { ru, en, uz } as const

const lazyLocales = import.meta.glob<{ default: Record<string, unknown> }>(
  './locales/*.json',
)

const loaded = new Set(Object.keys(CORE))

/** Fetch a locale's chunk and register it, unless it is already present. */
export async function loadLocale(locale: string): Promise<void> {
  if (loaded.has(locale) || !SUPPORTED_LOCALES.includes(locale)) return
  const loader = lazyLocales[`./locales/${locale}.json`]
  if (!loader) return
  try {
    const module = await loader()
    i18n.addResourceBundle(locale, 'translation', module.default, true, true)
    loaded.add(locale)
  } catch {
    /* Offline or a failed chunk: i18next keeps serving the fallback locale. */
  }
}

/**
 * Switch language, fetching its bundle first so the UI never flashes through
 * the fallback on the way.
 */
export async function changeLocale(locale: string): Promise<void> {
  await loadLocale(locale)
  await i18n.changeLanguage(locale)
}

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
  resources: Object.fromEntries(
    Object.entries(CORE).map(([code, translation]) => [code, { translation }]),
  ),
  lng: selected in CORE ? selected : DEFAULT_LOCALE,
  fallbackLng: DEFAULT_LOCALE,
  supportedLngs: SUPPORTED_LOCALES,
  load: 'currentOnly',
  interpolation: { escapeValue: false },
})

// A remembered non-core locale renders in Russian for one frame, then swaps in
// as soon as its chunk lands. Init stays synchronous so nothing can wedge the
// app behind a pending import.
if (!(selected in CORE)) void changeLocale(selected)

applyDocumentLocale(selected)
export default i18n

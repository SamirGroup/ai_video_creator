// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import i18n, { applyDocumentLocale, changeLocale } from './index'
import { LANGUAGES } from './registry'

afterEach(async () => {
  await i18n.changeLanguage('ru')
})

describe('locale selection', () => {
  it('exposes exactly 30 distinct locales', () => {
    expect(new Set(LANGUAGES.map((language) => language.code)).size).toBe(30)
  })
  it('switches all core navigation labels without falling back to a key', async () => {
    for (const language of LANGUAGES) {
      // changeLocale, not changeLanguage: non-core locales are code-split and
      // have to be fetched first, which is what the app itself does.
      await changeLocale(language.code)
      expect(i18n.hasResourceBundle(language.code, 'translation')).toBe(true)
      expect(i18n.getResource(language.code, 'translation', 'nav.language')).toBeTruthy()
      expect(i18n.t('nav.language')).not.toBe('nav.language')
      expect(document.documentElement.lang).toBe(language.code)
      expect(document.documentElement.dir).toBe(language.direction)
    }
  })
  it('preserves regional Arabic and resets direction when leaving RTL', () => {
    applyDocumentLocale('ar-EG')
    expect(document.documentElement.dir).toBe('rtl')
    expect(document.documentElement.lang).toBe('ar-EG')
    applyDocumentLocale('ru')
    expect(document.documentElement.dir).toBe('ltr')
    expect(localStorage.getItem('ai-youtuber-locale')).toBe('ru')
  })
})

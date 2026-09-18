import { MyWebParticleBackground } from './myweb-particle-background'
import { useUiStore } from '@/stores/uiStore'
import type { ReactNode } from 'react'
import { AuthOrbitBackground } from './modern-animated-sign-in'
import { Link } from 'react-router-dom'
import { ChevronLeft, Clapperboard } from 'lucide-react'
import { motion, useReducedMotion } from 'framer-motion'
import { useTranslation } from 'react-i18next'
import { LanguageSwitcher } from '@/components/layout/LanguageSwitcher'
import { ThemeToggle } from '@/components/layout/ThemeToggle'

/** Adapted from the supplied GridAuth component; real forms are passed as children. */
export default function AuthForm({ children }: { children: ReactNode }) {
  const { t } = useTranslation()
  const reduceMotion = useReducedMotion()
  const theme = useUiStore((s) => s.theme)
  return (
    <div className="auth-grid-shell relative isolate flex min-h-svh flex-col overflow-x-clip">
      {theme === 'light' && <MyWebParticleBackground />}
      <AuthOrbitBackground />
      <header className="flex flex-wrap items-center justify-between gap-3 px-5 py-5 sm:px-10">
        <Link
          to="/"
          className="auth-back inline-flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-sm text-foreground hover:bg-muted"
        >
          <ChevronLeft size={16} className="rtl:rotate-180" />
          {t('app.name')}
        </Link>
        <div className="flex items-center gap-2">
          <LanguageSwitcher />
          <ThemeToggle />
        </div>
      </header>
      <main className="flex flex-1 items-center justify-center px-5 py-10 sm:py-16">
        <motion.section
          initial={reduceMotion ? false : { opacity: 0, y: 25 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45, ease: 'easeInOut' }}
          className="auth-grid-card relative w-full max-w-md rounded-2xl p-6 sm:p-9"
        >
          <Link
            to="/"
            className="mb-8 flex items-center justify-center gap-3 text-xl font-bold text-foreground"
          >
            <span className="auth-brand-mark flex h-10 w-10 items-center justify-center rounded-xl text-white">
              <Clapperboard size={23} aria-hidden="true" />
            </span>
            {t('app.name')}
          </Link>
          {children}
        </motion.section>
      </main>
    </div>
  )
}

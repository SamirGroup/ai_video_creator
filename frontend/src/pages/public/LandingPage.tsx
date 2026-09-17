import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { LanguageSwitcher } from '@/components/layout/LanguageSwitcher'
import './landing.css'
import { ParticleGlobe } from './ParticleGlobe'

export function LandingPage() {
  const { t } = useTranslation()
  const services = t('landing.services', { returnObjects: true }) as {
    title: string
    text: string
  }[]
  const steps = t('landing.steps', { returnObjects: true }) as string[]
  const faqs = t('landing.faqs', { returnObjects: true }) as { q: string; a: string }[]
  return (
    <div className="marketing">
      <header className="marketing-nav">
        <Link to="/" className="marketing-logo">
          Creator<span>AI.</span>
        </Link>
        <nav aria-label={t('landing.navigation')}>
          <a href="#services">{t('landing.navServices')}</a>
          <a href="#process">{t('landing.navProcess')}</a>
          <a href="#share">{t('landing.navShare')}</a>
          <a href="#faq">FAQ</a>
        </nav>
        <div className="marketing-controls">
          <LanguageSwitcher />
          <Link to="/login" className="marketing-login">
            {t('auth.login.submit')} ↗
          </Link>
        </div>
      </header>
      <main>
        <section className="marketing-hero">
          <ParticleGlobe />
          <div className="marketing-hero-content">
            <span className="marketing-pill">{t('landing.badge')}</span>
            <h1>
              Creator AI
              <br />
              <em>{t('landing.heroAccent')}</em>
              <br />
              {t('landing.heroEnd')}
            </h1>
            <p>{t('landing.description')}</p>
            <Link className="marketing-button" to="/register">
              {t('landing.start')} <span>↗</span>
            </Link>
          </div>
          <a className="marketing-scroll" href="#services">
            ↓ <span>{t('landing.discover')}</span>
          </a>
        </section>
        <div className="marketing-strip">
          <span>YouTube</span>
          <span>AI VIDEO</span>
          <span>SHORTS</span>
          <span>ANALYTICS</span>
          <span>CREATOR STUDIO</span>
        </div>
        <section className="marketing-section" id="services">
          <p className="marketing-eyebrow">01 / {t('landing.navServices')}</p>
          <h2>
            {t('landing.servicesTitle')}
            <span>.</span>
          </h2>
          <p className="marketing-lead">{t('landing.servicesLead')}</p>
          <div className="marketing-grid">
            {services.map((service, i) => (
              <article className="marketing-card" key={service.title}>
                <div className="marketing-card-top">
                  <span>0{i + 1} / CREATOR AI</span>
                  <span className="marketing-symbol">{['✧', '▷', '◎', '↗'][i]}</span>
                </div>
                <h3>{service.title}</h3>
                <p>{service.text}</p>
                <a href="#process">{t('landing.discover')} ↗</a>
              </article>
            ))}
          </div>
        </section>
        <section className="marketing-section marketing-process" id="process">
          <p className="marketing-eyebrow">02 / {t('landing.navProcess')}</p>
          <h2>
            {t('landing.processTitle')}
            <span>.</span>
          </h2>
          <div className="marketing-steps">
            {steps.map((step, i) => (
              <div key={step}>
                <span>0{i + 1}</span>
                <h3>{step}</h3>
                <span aria-hidden="true">↗</span>
              </div>
            ))}
          </div>
        </section>
        <section className="marketing-section" id="share">
          <p className="marketing-eyebrow">03 / {t('landing.navShare')}</p>
          <h2>
            {t('landing.shareTitle')}
            <span>.</span>
          </h2>
          <div className="marketing-share">
            <div>
              <strong>
                70<span>%</span>
              </strong>
              <p>{t('landing.creatorShare')}</p>
            </div>
            <div>
              <strong>
                30<span>%</span>
              </strong>
              <p>{t('landing.platformShare')}</p>
            </div>
          </div>
          <p className="marketing-share-note">{t('landing.shareScope')}</p>
          <p className="marketing-lead">{t('landing.shareDetails')}</p>
        </section>
        <section className="marketing-section" id="faq">
          <p className="marketing-eyebrow">04 / FAQ</p>
          <h2>
            {t('landing.faqTitle')}
            <span>.</span>
          </h2>
          <div className="marketing-faq">
            {faqs.map((faq) => (
              <details key={faq.q}>
                <summary>
                  {faq.q}
                  <span aria-hidden="true">+</span>
                </summary>
                <p>{faq.a}</p>
              </details>
            ))}
          </div>
        </section>
        <section className="marketing-section marketing-cta">
          <span className="marketing-pill">CREATOR AI ECOSYSTEM</span>
          <h2>{t('landing.ctaTitle')}</h2>
          <p>{t('landing.ctaText')}</p>
          <Link className="marketing-button" to="/register">
            {t('landing.start')} ↗
          </Link>
        </section>
      </main>
      <footer className="marketing-footer">
        <Link to="/" className="marketing-logo">
          Creator<span>AI.</span>
        </Link>
        <p>{t('landing.footer')}</p>
        <div>
          <a href="#share">{t('landing.navShare')}</a>
          <Link to="/login">{t('auth.login.submit')}</Link>
        </div>
        <small>© {new Date().getFullYear()} Creator AI</small>
      </footer>
    </div>
  )
}

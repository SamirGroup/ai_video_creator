/* Website-development packages on the landing. Copy comes from window.__CA__
   (block `svc`, 30 locales); prices and terms come from the API, so the page
   always shows what the contract will say. Hidden if the API is unreachable. */
(() => {
  if (customElements.get('creator-services')) return
  let request
  const load = () => request || (request = fetch('/api/v1/public/web-services', { credentials: 'omit', cache: 'no-store' })
    .then(r => { if (!r.ok) throw Error('Unavailable'); return r.json() }).catch(() => null))
  const node = (tag, className, text) => { const el = document.createElement(tag); if (className) el.className = className; if (text != null) el.textContent = text; return el }
  const icon = path => { const s = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); s.setAttribute('viewBox', '0 0 24 24'); s.setAttribute('aria-hidden', 'true'); s.innerHTML = path; return s }
  const CHECK = '<path d="M20 6 9 17l-5-5" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>'
  const DOC = '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z M14 3v5h5 M9 13h6 M9 17h4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
  const SHIELD = '<path d="M12 3 5 6v5c0 4.5 3 8.3 7 10 4-1.7 7-5.5 7-10V6z M9 12l2 2 4-4" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>'
  const POPULAR = 'business'
  const money = value => '$' + Number(value).toLocaleString('en-US', { maximumFractionDigits: 0 })

  const css = `
    :host{display:block;position:relative;z-index:10;--gold:#ffc700;--ink:#0a0a0a;--muted:#52525b;--bg:#fff;--card:#fafafa;--line:rgba(10,10,10,.1);--pop:#fff7d6;color:var(--ink);background:var(--bg);font-family:inherit}
    /* A solid band: the page's animated backdrop would sit behind the copy otherwise. */
    :host([data-theme=dark]){--ink:#f4f4f5;--muted:#a1a1aa;--bg:#050505;--card:#131517;--line:rgba(255,255,255,.1);--pop:#1d1a0d}
    *{box-sizing:border-box}
    .section{max-width:1280px;margin:0 auto;padding:88px 24px 72px}
    .head{max-width:760px;margin:0 auto 36px;text-align:center}
    .eyebrow{display:inline-block;font-size:11px;letter-spacing:.24em;text-transform:uppercase;color:#b88a00;margin:0 0 14px}
    :host([data-theme=dark]) .eyebrow{color:var(--gold)}
    h2{font-size:clamp(28px,4.4vw,48px);line-height:1.08;font-weight:500;letter-spacing:-.03em;margin:0 0 14px}
    .lead{font-size:16px;line-height:1.65;color:var(--muted);margin:0}
    .trust{display:flex;flex-wrap:wrap;justify-content:center;gap:10px 22px;margin:22px 0 0;padding:0;list-style:none;font-size:13px;color:var(--muted)}
    .trust li{display:flex;align-items:center;gap:8px}.trust svg{width:18px;height:18px;color:#b88a00;flex:none}
    :host([data-theme=dark]) .trust svg{color:var(--gold)}
    .grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px}
    .card{position:relative;display:flex;flex-direction:column;border:1px solid var(--line);border-radius:22px;background:var(--card);padding:26px 22px 22px;transition:border-color .2s,transform .2s}
    .card:hover{border-color:color-mix(in srgb,var(--gold) 60%,transparent);transform:translateY(-2px)}
    .card.pop{border-color:var(--gold);background:var(--pop);box-shadow:0 18px 50px rgba(255,199,0,.14)}
    .badge{position:absolute;inset-block-start:-11px;inset-inline-start:22px;background:var(--gold);color:#0a0a0a;font-size:10px;font-weight:700;letter-spacing:.14em;text-transform:uppercase;padding:5px 10px;border-radius:999px}
    .name{font-size:11px;letter-spacing:.2em;text-transform:uppercase;color:var(--muted);margin:0}
    h3{font-size:19px;font-weight:600;margin:6px 0 0;letter-spacing:-.01em}
    .price{font-size:40px;font-weight:600;letter-spacing:-.04em;margin:18px 0 0;direction:ltr;text-align:start}
    ul.features{list-style:none;margin:20px 0 0;padding:0;display:grid;gap:10px;flex:1}
    ul.features li{display:flex;gap:10px;font-size:14px;line-height:1.45}
    ul.features svg{width:16px;height:16px;flex:none;margin-top:2px;color:#b88a00}
    :host([data-theme=dark]) ul.features svg{color:var(--gold)}
    dl{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:22px 0 0;padding:16px 0 0;border-top:1px solid var(--line)}
    dt{font-size:11px;color:var(--muted);margin:0}dd{font-size:13px;font-weight:600;margin:3px 0 0}
    a.cta{margin-top:20px;display:flex;align-items:center;justify-content:center;height:46px;border-radius:999px;font-size:14px;font-weight:600;text-decoration:none;border:1px solid var(--ink);color:var(--ink);transition:background .2s,color .2s}
    a.cta:hover{background:var(--ink);color:var(--card)}
    .pop a.cta{background:var(--gold);border-color:var(--gold);color:#0a0a0a}.pop a.cta:hover{filter:brightness(1.05);background:var(--gold);color:#0a0a0a}
    a:focus-visible{outline:2px solid var(--gold);outline-offset:3px}
    @media(max-width:1100px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
    @media(max-width:640px){.section{padding:64px 16px 48px}.grid{grid-template-columns:1fr}.price{font-size:34px}}
    @media(prefers-reduced-motion:reduce){.card,a.cta{transition:none}.card:hover{transform:none}}
  `

  class Services extends HTMLElement {
    connectedCallback() {
      const root = document.documentElement
      this.observer = new MutationObserver(() => this.update())
      this.observer.observe(root, { attributes: true, attributeFilter: ['lang', 'class'] })
      load().then(data => { if (this.isConnected && data?.packages?.length) { this.data = data; this.update() } })
    }
    disconnectedCallback() { this.observer?.disconnect() }
    update() {
      const root = document.documentElement
      this.dataset.theme = root.classList.contains('dark') ? 'dark' : 'light'
      const lang = root.getAttribute('lang') || 'en'
      if (!this.data || this.renderedLang === lang) return
      this.renderedLang = lang
      this.render(window.__CA__?.block('svc')[lang])
    }
    render(t) {
      if (!t) return
      const shadow = this.shadowRoot || this.attachShadow({ mode: 'open' })
      shadow.replaceChildren()
      const style = node('style'); style.textContent = css
      const section = node('section', 'section'); section.id = 'web-services'; section.setAttribute('aria-labelledby', 'svc-title')
      const head = node('div', 'head')
      const title = node('h2', '', t.title); title.id = 'svc-title'
      const trust = node('ul', 'trust')
      for (const [svg, text] of [[DOC, t.contract], [SHIELD, t.payment]]) { const li = node('li'); li.append(icon(svg), node('span', '', text)); trust.append(li) }
      head.append(node('p', 'eyebrow', t.label), title, node('p', 'lead', t.lead), trust)
      const grid = node('div', 'grid'); grid.setAttribute('role', 'list')
      const m = t.metric
      for (const pkg of this.data.packages) {
        const copy = t.packages[pkg.code]; if (!copy) continue
        const card = node('article', 'card' + (pkg.code === POPULAR ? ' pop' : '')); card.setAttribute('role', 'listitem')
        if (pkg.code === POPULAR) card.append(node('span', 'badge', t.popular))
        const features = node('ul', 'features')
        for (const f of copy.features) { const li = node('li'); li.append(icon(CHECK), node('span', '', f)); features.append(li) }
        const dl = node('dl')
        for (const [label, value] of [
          [m.delivery, m.days.replace('{{n}}', pkg.delivery_days)],
          [m.pages, pkg.page_limit ? String(pkg.page_limit) : m.bySpec],
          [m.revisions, String(pkg.revision_rounds)],
          [m.support, m.months.replace('{{n}}', pkg.support_months)],
        ]) { const d = node('div'); d.append(node('dt', '', label), node('dd', '', value)); dl.append(d) }
        const cta = node('a', 'cta', t.cta); cta.href = `/web-services?package=${encodeURIComponent(pkg.code)}`
        cta.setAttribute('aria-label', `${t.cta}: ${copy.name} — ${money(pkg.price_usd)}`)
        card.append(node('p', 'name', copy.name), node('h3', '', copy.tagline), node('p', 'price', money(pkg.price_usd)), features, dl, cta)
        grid.append(card)
      }
      section.append(head, grid)
      shadow.append(style, section)
    }
  }
  customElements.define('creator-services', Services)
})()

/* Public, admin-managed partner banner. No visitor tracking or third-party scripts. */
(() => {
  if (customElements.get('creator-partners')) return
  let request
  const load = () => request || (request = fetch('/api/v1/public/partners', { credentials: 'omit', cache: 'no-store' }).then(r => { if (!r.ok) throw Error('Unavailable'); return r.json() }).catch(() => null))
  const node = (tag, className, text) => { const el = document.createElement(tag); if (className) el.className = className; if (text) el.textContent = text; return el }
  const safe = value => { try { const u = new URL(value); return u.protocol === 'https:' && !u.username && !u.password ? u.href : '' } catch { return '' } }
  class Partners extends HTMLElement {
    connectedCallback() {
      this.rendered = false
      load().then(data => { if (this.isConnected && !this.rendered && data?.banner?.enabled && data.partners?.length) this.render(data) })
    }
    disconnectedCallback() { this.observer?.disconnect() }
    render({ banner, partners }) {
      this.rendered = true
      const root = this.shadowRoot || this.attachShadow({ mode: 'open' })
      root.replaceChildren()
      const style = node('style')
      style.textContent = `
        :host{display:block;position:relative;z-index:10;isolation:isolate;color:#f4f4f5;font-family:inherit}*{box-sizing:border-box}
        .section{max-width:1280px;margin:0 auto;padding:30px 24px 56px}.panel{position:relative;overflow:hidden;border:1px solid color-mix(in srgb,currentColor 14%,transparent);border-radius:24px;background:#181c1f;box-shadow:0 18px 50px #00000020;padding:28px 0}
        .heading{display:flex;align-items:flex-start;justify-content:space-between;gap:20px;padding:0 28px 22px}.eyebrow{font-size:10px;text-transform:uppercase;letter-spacing:.22em;color:#e1b84e;margin:0 0 10px}.title{font-size:clamp(22px,3vw,32px);font-weight:500;letter-spacing:-.03em;margin:0 0 8px}.subtitle{font-size:14px;line-height:1.6;opacity:.65;margin:0;max-width:680px}
        button{font:inherit;font-size:12px;border:1px solid color-mix(in srgb,currentColor 20%,transparent);color:inherit;background:transparent;border-radius:999px;padding:9px 14px;cursor:pointer;white-space:nowrap}button:hover{background:color-mix(in srgb,currentColor 8%,transparent)}button:focus-visible,a:focus-visible{outline:2px solid #d7aa25;outline-offset:4px}
        .viewport{overflow:hidden}.track{display:flex;width:max-content;animation:partner-slide var(--duration,35s) linear infinite}.group{display:flex;align-items:stretch;gap:16px;padding:6px 8px;flex-shrink:0}.item{width:218px;display:flex;flex-direction:column;align-items:center;text-align:center;gap:10px;padding:20px 16px;border:1px solid color-mix(in srgb,currentColor 12%,transparent);border-radius:16px;text-decoration:none;color:inherit;transition:border-color .2s,background .2s}.item:hover{border-color:#c8a43b;background:color-mix(in srgb,currentColor 6%,transparent)}
        .logo{height:66px;width:160px;padding:10px;display:flex;align-items:center;justify-content:center;border-radius:10px;background:white}.logo img{max-width:100%;max-height:100%;object-fit:contain}.name{font-size:14px;font-weight:600;overflow-wrap:anywhere}.caption{font-size:12px;line-height:1.5;opacity:.65;overflow-wrap:anywhere}.disclosure{font-size:11px;line-height:1.5;opacity:.6;padding:20px 28px 0;margin:0}
        .viewport:hover .track,.viewport:focus-within .track,.paused .track{animation-play-state:paused}
        .static .track{animation:none;width:100%}.static .group{width:100%;flex-wrap:wrap;justify-content:center;padding:6px 20px}.static .clone{display:none}
        @keyframes partner-slide{to{transform:translateX(-50%)}}
        @media(prefers-reduced-motion:reduce){.track{animation:none!important;width:100%}.group{width:100%;flex-wrap:wrap;justify-content:center}.clone{display:none}.item{transition:none}}
        @media(max-width:600px){.section{padding:20px 16px 36px}.panel{border-radius:18px;padding:22px 0}.heading{padding:0 20px 20px;flex-wrap:wrap}.item{width:180px;padding:16px 10px}.logo{width:140px}.disclosure{padding:18px 20px 0}.static .item{width:min(100%,240px)}}
      `
      const section = node('section','section'); section.setAttribute('aria-label', banner.title || 'Hamkorlarimiz')
      const panel=node('div','panel'), heading=node('div','heading'), copy=node('div')
      copy.append(node('p','eyebrow','Hamkorlik · Reklama'),node('h2','title',banner.title),node('p','subtitle',banner.subtitle))
      const pause=node('button','','Animatsiyani to‘xtatish'); pause.type='button'; pause.setAttribute('aria-pressed','false')
      pause.addEventListener('click',()=>{ const stopped=panel.classList.toggle('paused'); pause.textContent=stopped?'Animatsiyani davom ettirish':'Animatsiyani to‘xtatish';pause.setAttribute('aria-pressed',String(stopped)) })
      heading.append(copy,pause)
      const viewport=node('div','viewport'), track=node('div','track'), group=node('div','group')
      group.setAttribute('role','list')
      track.style.setProperty('--duration',`${Math.max(15,Math.min(120,Number(banner.animation_seconds)||35))}s`)
      for (const p of partners) {
        const href=safe(p.link_url), src=safe(p.image_url); if (!href || !src) continue
        const item=node('a','item');item.href=href;item.target='_blank';item.rel='sponsored noopener noreferrer';item.setAttribute('aria-label',`${p.name} — yangi oynada ochiladi`)
        const logo=node('div','logo'), image=node('img');image.src=src;image.alt=p.name;image.loading='lazy';image.decoding='async';image.referrerPolicy='no-referrer'
        image.addEventListener('error',()=>{logo.hidden=true})
        logo.append(image);item.append(logo,node('span','name',p.name));if(p.caption)item.append(node('span','caption',p.caption));const entry=node('div');entry.setAttribute('role','listitem');entry.append(item);group.append(entry)
      }
      if (!group.children.length) return
      const clone=group.cloneNode(true);clone.classList.add('clone');clone.setAttribute('aria-hidden','true');clone.inert=true
      clone.querySelectorAll('a').forEach(a=>a.tabIndex=-1)
      clone.querySelectorAll('img').forEach(img=>img.addEventListener('error',()=>{img.parentElement.hidden=true}))
      track.append(group,clone);viewport.append(track);panel.append(heading,viewport)
      if(partners.some(p=>p.is_affiliate)) panel.append(node('p','disclosure','Referral havolalari mavjud: ushbu havolalar orqali xarid qilsangiz, biz komissiya olishimiz mumkin.'))
      section.append(panel);root.append(style,section)
      const reduced=window.matchMedia('(prefers-reduced-motion: reduce)')
      const update=()=>{panel.classList.remove('static');const fits=group.scrollWidth<=viewport.clientWidth; const fixed=!banner.animation_enabled||reduced.matches||fits;panel.classList.toggle('static',fixed);pause.hidden=fixed}
      this.observer=new ResizeObserver(update);this.observer.observe(viewport);update()
      reduced.addEventListener('change',update,{signal:(this.controller=new AbortController()).signal})
    }
  }
  const disconnect=Partners.prototype.disconnectedCallback
  Partners.prototype.disconnectedCallback=function(){disconnect.call(this);this.controller?.abort()}
  customElements.define('creator-partners',Partners)
})()

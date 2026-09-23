import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, ArrowUpRight, Cloud, KeyRound, UserRound, X } from 'lucide-react'

type Method = 'choose' | 'subscription' | 'cloud'

export function ClaudeConnectionOptions({ onApi }: { onApi: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null)
  const [method, setMethod] = useState<Method>('choose')
  useEffect(() => {
    const node = dialog.current
    return () => node?.close()
  }, [])
  function close() {
    dialog.current?.close()
    setMethod('choose')
  }
  const link =
    'flex w-full items-center justify-between gap-3 rounded-xl border border-border bg-muted/40 px-4 py-3 text-start text-sm font-medium transition hover:bg-muted focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary'
  return (
    <>
      <button
        type="button"
        className="rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground"
        onClick={() => {
          setMethod('choose')
          dialog.current?.showModal()
        }}
      >
        Ulanish usulini tanlash
      </button>
      <dialog
        ref={dialog}
        aria-labelledby="claude-connect-title"
        aria-describedby="claude-connect-description"
        onCancel={() => setMethod('choose')}
        className="fixed inset-0 m-auto max-h-[90dvh] w-[calc(100%_-_2rem)] max-w-lg overflow-y-auto rounded-2xl border border-border bg-card p-0 text-foreground shadow-2xl backdrop:bg-black/70"
      >
        <div className="relative p-5 sm:p-7">
          <button
            type="button"
            aria-label="Ulanish oynasini yopish"
            onClick={close}
            className="absolute right-3 top-3 rounded-md p-2 text-muted-foreground hover:bg-muted"
          >
            <X size={18} />
          </button>
          <div className="mb-5 flex size-12 items-center justify-center rounded-xl border border-primary/25 bg-primary/10 text-primary">
            <KeyRound size={23} />
          </div>
          <h2 id="claude-connect-title" className="pr-6 text-xl font-semibold">
            Claude’ga qanday ulanasiz?
          </h2>
          <p
            id="claude-connect-description"
            className="mt-2 text-sm leading-relaxed text-muted-foreground"
          >
            Ekotizim assistenti uchun API kalitini ulang yoki Claude obunasining kirish
            imkoniyatlarini ko‘ring.
          </p>
          {method === 'choose' ? (
            <div className="mt-6 space-y-3">
              <button
                type="button"
                className={link}
                onClick={() => {
                  close()
                  onApi()
                }}
              >
                <span className="flex items-start gap-3">
                  <KeyRound size={19} className="mt-0.5 shrink-0 text-primary" />
                  <span>
                    Anthropic Console · API key
                    <span className="mt-1 block text-xs font-normal text-muted-foreground">
                      Mijozlar assistenti · foydalanish bo‘yicha to‘lov
                    </span>
                  </span>
                </span>
                <ArrowUpRight size={17} className="shrink-0" />
              </button>
              <button
                type="button"
                className={link}
                onClick={() => setMethod('subscription')}
              >
                <span className="flex items-start gap-3">
                  <UserRound size={19} className="mt-0.5 shrink-0" />
                  <span>
                    Claude.ai Subscription
                    <span className="mt-1 block text-xs font-normal text-muted-foreground">
                      Rasmiy Claude / Claude Code hisobiga kirish
                    </span>
                  </span>
                </span>
                <ArrowUpRight size={17} className="shrink-0" />
              </button>
              <button type="button" className={link} onClick={() => setMethod('cloud')}>
                <span className="flex items-start gap-3">
                  <Cloud size={19} className="mt-0.5 shrink-0" />
                  <span>
                    Bedrock, Foundry yoki Vertex
                    <span className="mt-1 block text-xs font-normal text-muted-foreground">
                      Alohida sozlash kerak · hozir ulanmagan
                    </span>
                  </span>
                </span>
                <ArrowUpRight size={17} className="shrink-0" />
              </button>
              <button
                type="button"
                onClick={close}
                className="w-full rounded-xl px-4 py-3 text-sm text-muted-foreground hover:bg-muted"
              >
                Bekor qilish
              </button>
            </div>
          ) : (
            <div className="mt-6 space-y-4">
              <button
                type="button"
                onClick={() => setMethod('choose')}
                className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground"
              >
                <ArrowLeft size={16} />
                Barcha variantlar
              </button>
              {method === 'subscription' ? (
                <>
                  <h3 className="font-semibold">Claude.ai Subscription</h3>
                  <p className="text-sm leading-relaxed text-muted-foreground">
                    Pro, Max, Team yoki Enterprise hisobingizga Anthropic’ning rasmiy
                    oynasida kirasiz. Claude Code’da rasmdagi “Claude.ai Subscription”
                    tugmasidan foydalaning.
                  </p>
                  <div className="rounded-xl border border-border bg-muted/40 p-4 text-sm leading-relaxed">
                    Bu kirish Creator AI mijozlar assistentini faollashtirmaydi. Bitta
                    obunani barcha mijozlarga ulash uchun qo‘llab-quvvatlanadigan
                    integratsiya yo‘q. Ekotizim assistenti uchun API key tanlang.
                  </div>
                  <a
                    className={link}
                    href="https://claude.ai/login"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Rasmiy Claude hisobiga kirish
                    <ArrowUpRight size={17} />
                  </a>
                  <a
                    className="block text-sm text-primary underline"
                    href="https://code.claude.com/docs/en/legal-and-compliance#authentication-and-credential-use"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Obuna va integratsiya imkoniyatlari
                  </a>
                </>
              ) : (
                <>
                  <h3 className="font-semibold">Bulut provayderlari</h3>
                  <p className="text-sm leading-relaxed text-muted-foreground">
                    AWS Bedrock, Microsoft Foundry yoki Google Vertex AI alohida hisob va
                    ulanish sozlamalarini talab qiladi. Ushbu platformada bu adapterlar
                    hali o‘rnatilmagan.
                  </p>
                  <a
                    className={link}
                    href="https://code.claude.com/docs/en/third-party-integrations"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    Rasmiy ulanish yo‘riqnomasi
                    <ArrowUpRight size={17} />
                  </a>
                </>
              )}
              <button
                type="button"
                className="w-full rounded-xl bg-primary px-4 py-3 text-sm font-semibold text-primary-foreground"
                onClick={() => {
                  close()
                  onApi()
                }}
              >
                API key orqali ulash
              </button>
            </div>
          )}
        </div>
      </dialog>
    </>
  )
}

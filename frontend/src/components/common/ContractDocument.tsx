import type { Clause, ContractDocument as Doc } from '@/api/webServices'

/**
 * Lays out a website-service contract as an A4 document. All wording comes
 * from the backend snapshot the customer accepted; nothing here is contract
 * text, so the page is always the exact document on record.
 */

const TASHKENT = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Asia/Tashkent',
  day: '2-digit',
  month: '2-digit',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
})

function day(iso: string) {
  const [y, m, d] = iso.split('-')
  return y && m && d ? `${d}.${m}.${y}` : iso
}

function ClauseBody({ clause }: { clause: Clause }) {
  if (typeof clause === 'string') return <>{clause}</>
  return (
    <>
      {clause.text}
      <ul className="mt-1 list-none space-y-0.5 pl-6">
        {clause.items.map((item) => (
          <li
            key={item}
            className="relative before:absolute before:-left-4 before:content-['—']"
          >
            {item}
          </li>
        ))}
      </ul>
    </>
  )
}

function Requisites({ title, rows }: { title: string; rows: [string, string][] }) {
  return (
    <div className="flex-1 break-inside-avoid">
      <p className="mb-2 text-center font-bold tracking-wide">{title}</p>
      <table className="w-full border-collapse text-[12px]">
        <tbody>
          {rows.map(([label, value]) => (
            <tr key={label} className="align-top">
              <td className="w-[38%] border border-neutral-400 px-2 py-1 text-neutral-600">
                {label}
              </td>
              <td className="border border-neutral-400 px-2 py-1 break-words">{value}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function ContractDocument({ doc }: { doc: Doc }) {
  const l = doc.labels
  const accepted = doc.acceptance
  return (
    <article
      lang={doc.language}
      className="contract-paper relative mx-auto w-full max-w-[210mm] bg-white px-[16mm] py-[18mm] font-serif text-[13px] leading-relaxed text-neutral-900 shadow-lg print:max-w-none print:p-0 print:shadow-none"
    >
      <style>{`@page { size: A4; margin: 16mm 16mm 18mm; }
        @media print { html, body { background: #fff !important; color-scheme: light } body * { visibility: hidden } .contract-paper, .contract-paper * { visibility: visible }
          .contract-paper { position: absolute; inset: 0 auto auto 0; width: 100% } }`}</style>
      {!accepted && (
        <p className="mb-6 border-2 border-dashed border-amber-600 p-2 text-center font-sans text-xs font-semibold uppercase tracking-widest text-amber-700">
          {l.draft}
        </p>
      )}

      <header className="text-center">
        <h1 className="text-[15px] font-bold uppercase leading-snug tracking-wide">
          {doc.title}
        </h1>
        <p className="mt-1 font-bold">
          {l.number} {doc.number || '________'}
        </p>
      </header>
      <div className="mt-5 flex justify-between">
        <span>{doc.city}</span>
        <span>{doc.date ? day(doc.date) : '«___» ________ 20__'}</span>
      </div>

      <p className="mt-5 indent-8 text-justify">{doc.preamble}</p>

      {doc.sections.map((section, s) => (
        <section key={section.title} className="mt-5">
          <h2 className="mb-2 text-center font-bold uppercase">
            {s + 1}. {section.title}
          </h2>
          {section.clauses.map((clause, c) => (
            <div key={c} className="mb-1.5 text-justify">
              <span className="font-semibold">
                {s + 1}.{c + 1}.
              </span>{' '}
              <ClauseBody clause={clause} />
            </div>
          ))}
        </section>
      ))}

      <section className="mt-6 break-inside-avoid">
        <h2 className="mb-3 text-center font-bold uppercase">
          {doc.sections.length + 1}. {l.requisites}
        </h2>
        <div className="flex flex-col gap-4 sm:flex-row print:flex-row">
          <Requisites title={l.executor} rows={doc.executor_rows} />
          <Requisites title={l.customer} rows={doc.customer_rows} />
        </div>
        <div className="mt-8 flex flex-col gap-8 sm:flex-row print:flex-row">
          <div className="flex-1">
            <p>{l.executor}</p>
            <p className="mt-8">____________________ / {doc.executor_signatory}</p>
            <p className="mt-1 text-xs text-neutral-600">{l.stamp}</p>
          </div>
          <div className="flex-1">
            <p>{l.customer}</p>
            <p className="mt-8">____________________ / {doc.customer_signatory}</p>
          </div>
        </div>
      </section>

      <section className="mt-10 break-before-page">
        <p className="text-right text-xs">
          {l.number} {doc.number || '________'}
        </p>
        <h2 className="my-3 text-center font-bold uppercase">{doc.annex_title}</h2>
        <table className="w-full border-collapse text-[12px]">
          <tbody>
            {[
              ...doc.annex_rows,
              [l.price, `${doc.price} ${doc.currency}`] as [string, string],
            ].map(([label, value]) => (
              <tr key={label}>
                <td className="w-[38%] border border-neutral-400 px-2 py-1 text-neutral-600">
                  {label}
                </td>
                <td className="border border-neutral-400 px-2 py-1">{value}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-4 font-semibold">{doc.annex_label}:</p>
        <p className="mt-1 whitespace-pre-wrap text-justify">{doc.annex_description}</p>
      </section>

      {accepted && (
        <footer className="mt-10 break-inside-avoid rounded border border-neutral-400 p-3 font-sans text-[11px] leading-5 text-neutral-700">
          <p className="font-semibold uppercase tracking-wide">{l.acceptance}</p>
          <p>
            {l.accepted_at}:{' '}
            {TASHKENT.format(new Date(accepted.accepted_at)).replace(/\//g, '.')} (UTC+5)
          </p>
          {accepted.ip && (
            <p>
              {l.ip}: {accepted.ip}
            </p>
          )}
          <p className="break-all">
            {l.hash}: <span className="font-mono">{accepted.checksum}</span>
          </p>
        </footer>
      )}
    </article>
  )
}

import { Fragment, type ReactNode } from 'react';
import { Star } from 'lucide-react';

/**
 * Konu anlatımı metni için küçük, güvenli bir biçimlendirici (HTML enjekte edilmez; her şey
 * React öğesi olarak kurulur).
 *
 * Biçim — bloklar boş satırla ayrılır:
 *   "### Başlık"          ara başlık
 *   "- madde"             madde listesi (ardışık satırlar)
 *   "| a | b |"           tablo; ilk satır başlık, "|---|" ayraç satırı yok sayılır
 *   "! metin"             "Sınavda" kutusu (blok başında; içinde madde/tablo olabilir)
 *   diğer satırlar        paragraf (tek satır sonu korunur)
 *   **kalın**             satır içi vurgu
 */
export function RichText({ text }: { text: string }) {
  const blocks = text.replace(/\r\n/g, '\n').split(/\n\s*\n/).map((b) => b.trim()).filter(Boolean);
  return (
    <div className="flex flex-col gap-3">
      {blocks.map((block, i) =>
        block.startsWith('! ') ? (
          <aside
            key={i}
            data-exam-tip
            className="flex gap-2.5 rounded-xl border border-duo-gold/40 bg-duo-gold-light p-3.5 text-duo-gray-700"
          >
            <Star className="mt-0.5 h-4 w-4 shrink-0 fill-duo-gold text-duo-gold" aria-hidden />
            <div className="flex min-w-0 flex-col gap-2">
              <span className="text-xs font-semibold text-duo-gold-dark">Sınavda</span>
              <Lines lines={block.slice(2).split('\n')} />
            </div>
          </aside>
        ) : (
          <Lines key={i} lines={block.split('\n')} />
        )
      )}
    </div>
  );
}

type Segment =
  | { type: 'p'; lines: string[] }
  | { type: 'h'; text: string }
  | { type: 'ul'; items: string[] }
  | { type: 'table'; rows: string[][] };

const BULLET = /^\s*[-•]\s+/;
const TABLE_SEP = /^\|?\s*:?-{2,}/;

function segment(lines: string[]): Segment[] {
  const out: Segment[] = [];
  for (const raw of lines) {
    const line = raw.trimEnd();
    const last = out[out.length - 1];
    if (line.startsWith('### ')) {
      out.push({ type: 'h', text: line.slice(4) });
    } else if (BULLET.test(line)) {
      const item = line.replace(BULLET, '');
      if (last?.type === 'ul') last.items.push(item);
      else out.push({ type: 'ul', items: [item] });
    } else if (line.trimStart().startsWith('|')) {
      if (TABLE_SEP.test(line.trim())) continue;
      const cells = line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim());
      if (last?.type === 'table') last.rows.push(cells);
      else out.push({ type: 'table', rows: [cells] });
    } else if (line.trim()) {
      if (last?.type === 'p') last.lines.push(line.trim());
      else out.push({ type: 'p', lines: [line.trim()] });
    }
  }
  return out;
}

function Lines({ lines }: { lines: string[] }) {
  return (
    <>
      {segment(lines).map((seg, i) => {
        if (seg.type === 'h') {
          return (
            <h3 key={i} className="pt-1 text-base font-semibold text-duo-blue-dark">
              {inline(seg.text)}
            </h3>
          );
        }
        if (seg.type === 'ul') {
          return (
            <ul key={i} className="flex list-disc flex-col gap-1.5 pl-5 text-base leading-[1.65] text-duo-gray-700 marker:text-duo-gray-300">
              {seg.items.map((item, j) => (
                <li key={j}>{inline(item)}</li>
              ))}
            </ul>
          );
        }
        if (seg.type === 'table') {
          const [head, ...body] = seg.rows;
          return (
            <div key={i} className="overflow-x-auto rounded-xl border border-duo-gray-100">
              <table className="w-full border-collapse text-left text-[15px] leading-snug tabular-nums">
                <thead className="border-b border-duo-gray-100 bg-duo-gray-50">
                  <tr>
                    {head.map((cell, j) => (
                      <th key={j} className="px-3 py-2 font-semibold text-duo-gray-700">
                        {inline(cell)}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {body.map((row, r) => (
                    <tr key={r} className="border-t border-duo-gray-100 align-top even:bg-duo-gray-50/60">
                      {row.map((cell, j) => (
                        <td key={j} className={j === 0 ? 'px-3 py-2 font-medium text-duo-gray-900' : 'px-3 py-2 text-duo-gray-700'}>
                          {inline(cell)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        }
        return (
          <p key={i} className="text-base leading-[1.65] text-duo-gray-700">
            {seg.lines.map((l, j) => (
              <Fragment key={j}>
                {j > 0 && <br />}
                {inline(l)}
              </Fragment>
            ))}
          </p>
        );
      })}
    </>
  );
}

/** **kalın** vurguları <strong>'a çevirir. */
function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith('**') && part.endsWith('**') && part.length > 4 ? (
      <strong key={i} className="font-semibold text-duo-gray-900">
        {part.slice(2, -2)}
      </strong>
    ) : (
      <Fragment key={i}>{part}</Fragment>
    )
  );
}

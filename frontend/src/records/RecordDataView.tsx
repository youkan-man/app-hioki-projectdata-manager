import { useEffect, useState } from 'react'
import { Button } from '../components'
import { download, json, query, type RecordFile, type RowPage } from './api'

export function RecordDataView({ item, onClose }: { item: RecordFile; onClose: () => void }) {
  const [table, setTable] = useState(0), [page, setPage] = useState(0), [search, setSearch] = useState('')
  const [column, setColumn] = useState<number | undefined>(), [descending, setDescending] = useState(false)
  const [after, setAfter] = useState(''), [before, setBefore] = useState('')
  const [data, setData] = useState<RowPage | null>(null), [error, setError] = useState(''), [loading, setLoading] = useState(false)
  const [exporting, setExporting] = useState(false)
  const info = item.inspection.tables[table]
  const filters = query({ search, column, descending, after: after ? new Date(after).toISOString() : undefined, before: before ? new Date(before).toISOString() : undefined })
  useEffect(() => {
    setPage(0)
  }, [filters, table])
  useEffect(() => {
    if (!info) return
    const controller = new AbortController(); setLoading(true); setError(''); setData(null)
    const timer = setTimeout(() => { void json<RowPage>(`/${item.id}/tables/${table}/rows?${filters}&offset=${page * 100}`, { signal: controller.signal }).then(setData).catch((e: Error) => { if (e.name !== 'AbortError') setError(e.message) }).finally(() => { if (!controller.signal.aborted) setLoading(false) }) }, 150)
    return () => { clearTimeout(timer); controller.abort() }
  }, [item.id, item.revision, table, filters, page, info])
  return <section className="panel record-data" aria-label="記録データ">
    <header className="record-detail-header"><h2>{item.name}</h2><Button onClick={onClose}>詳細を閉じる</Button></header>
    <dl className="record-metadata"><dt>ファイル</dt><dd>{item.filename}</dd><dt>SHA-256</dt><dd className="record-hash">{item.sha256}</dd><dt>メモ</dt><dd>{item.note || '—'}</dd><dt>日時の出典</dt><dd>{{ unknown: '不明', manual: '手動入力', table: '内部の表', 'companion-csv': '関連付けCSV' }[item.time_source] ?? item.time_source}</dd></dl>
    {item.inspection.message && <p role="status" className="record-warning">{item.inspection.message}</p>}
    {item.inspection.warnings.map((message) => <p key={message} className="record-warning">{message}</p>)}
    {info && <>
      <div className="record-toolbar"><label>表<select value={table} onChange={(e) => { setTable(Number(e.target.value)); setColumn(undefined); setAfter(''); setBefore(''); setPage(0) }}>{item.inspection.tables.map((t) => <option key={t.index} value={t.index}>{t.name}（{t.row_count.toLocaleString()} 行）</option>)}</select></label>
        <label>表内検索<input type="search" value={search} maxLength={255} onChange={(e) => setSearch(e.target.value)} /></label>
        <Button disabled={loading || exporting || !!error} onClick={() => { setExporting(true); void download(`/${item.id}/tables/${table}/csv?${filters}`, `${item.name}-${table}.csv`).catch((e: Error) => setError(e.message)).finally(() => setExporting(false)) }}>{exporting ? '出力中…' : '絞り込み結果をCSV出力'}</Button>
      </div>
      {info.time_column && <div className="record-toolbar"><span>記録範囲（{Intl.DateTimeFormat().resolvedOptions().timeZone}）</span><label>開始<input type="datetime-local" step="0.001" value={after} onChange={(e) => setAfter(e.target.value)} /></label><label>終了<input type="datetime-local" step="0.001" value={before} onChange={(e) => setBefore(e.target.value)} /></label><Button onClick={() => { setAfter(''); setBefore('') }}>期間を解除</Button></div>}
      {error && <p role="alert" className="record-error">{error}</p>}
      <div className="record-grid" aria-busy={loading}>{loading ? <p role="status">データを読み込み中…</p> : data && <table><thead><tr>{data.columns.map((name, index) => <th key={name} aria-sort={column === index ? descending ? 'descending' : 'ascending' : 'none'}><button onClick={() => { setColumn(index); setDescending(column === index ? !descending : false) }}>{name}{column === index ? descending ? ' ▼' : ' ▲' : ''}</button></th>)}</tr></thead><tbody>{data.rows.map((row, index) => <tr key={data.offset + index}>{row.map((value, j) => <td key={j}>{value}</td>)}</tr>)}</tbody></table>}</div>
      <div className="record-pagination"><Button disabled={page === 0 || loading} onClick={() => setPage(page - 1)}>前へ</Button><span>{data ? `${data.total.toLocaleString()} 行中 ${data.total ? data.offset + 1 : 0}–${data.offset + data.rows.length}` : '—'}</span><Button disabled={!data || (page + 1) * 100 >= data.total || loading} onClick={() => setPage(page + 1)}>次へ</Button></div>
    </>}
  </section>
}

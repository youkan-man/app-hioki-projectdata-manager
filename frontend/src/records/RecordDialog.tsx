import { useEffect, useRef, useState, type ReactNode } from 'react'
import type { Project } from '../types'
import { Button } from '../components'
import { json, type RecordFile } from './api'

export function Dialog({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    ref.current?.showModal()
    return () => { if (previous?.isConnected) previous.focus() }
  }, [])
  return <dialog ref={ref} className="record-dialog" onCancel={(e) => { e.preventDefault(); onClose() }}><header><h2>{title}</h2><button type="button" className="icon-button" onClick={onClose} aria-label="閉じる">×</button></header>{children}</dialog>
}

function localTime(value: string | null) {
  if (!value) return ''
  const date = new Date(value)
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 23)
}
export function RecordDialog({ item, projects, mode, onClose, onSaved }: { item: RecordFile; projects: Project[]; mode: 'edit' | 'csv' | 'delete'; onClose: () => void; onSaved: () => Promise<void> }) {
  const [busy, setBusy] = useState(false), [error, setError] = useState('')
  const [name, setName] = useState(item.name), [note, setNote] = useState(item.note)
  const [projectId, setProjectId] = useState(item.project_id ?? '')
  const [start, setStart] = useState(localTime(item.started_at)), [end, setEnd] = useState(localTime(item.ended_at))
  const [file, setFile] = useState<File | null>(null), [encoding, setEncoding] = useState('utf-8-sig')
  const [timeColumn, setTimeColumn] = useState(''), [zone, setZone] = useState('Asia/Tokyo')
  const browserZone = Intl.DateTimeFormat().resolvedOptions().timeZone
  const close = () => { if (!busy) onClose() }
  return <Dialog title={mode === 'edit' ? '記録を編集' : mode === 'csv' ? 'CSVを関連付け' : '記録を削除'} onClose={close}>
    <form onSubmit={(event) => { event.preventDefault(); setBusy(true); setError(''); void (async () => {
      try {
        if (mode === 'edit') {
          const update: Record<string, unknown> = { revision: item.revision, name, note, project_id: projectId || null }
          if (start !== localTime(item.started_at)) update.started_at = start ? new Date(start).toISOString() : null
          if (end !== localTime(item.ended_at)) update.ended_at = end ? new Date(end).toISOString() : null
          await json(`/${item.id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(update) })
        } else if (mode === 'csv') {
          if (!file) throw new Error('CSVファイルを選択してください。')
          const form = new FormData(); form.append('data', file); form.append('revision', String(item.revision)); form.append('encoding', encoding)
          if (timeColumn) { form.append('time_column', timeColumn); form.append('zone', zone) }
          await json(`/${item.id}/companion-csv`, { method: 'POST', body: form })
        } else await json(`/${item.id}?revision=${item.revision}`, { method: 'DELETE' })
        await onSaved(); onClose()
      } catch (e) { setError(e instanceof Error ? e.message : '保存に失敗しました。') }
      finally { setBusy(false) }
    })() }}>
      {mode === 'edit' ? <div className="record-form-grid">
        <label>記録名<input required maxLength={255} value={name} onChange={(e) => setName(e.target.value)} /></label>
        <label>プロジェクト<select value={projectId} onChange={(e) => setProjectId(e.target.value)}><option value="">未関連付け</option>{projects.map((p) => <option key={p.id} value={p.id} disabled={!!p.deletedAt}>{p.displayName}{p.deletedAt ? '（削除済み）' : ''} · {p.sourceUuid.slice(0, 8)}</option>)}</select></label>
        <label>記録開始（{browserZone}）<input type="datetime-local" step="0.001" value={start} onChange={(e) => setStart(e.target.value)} /></label>
        <label>記録終了（{browserZone}）<input type="datetime-local" step="0.001" value={end} onChange={(e) => setEnd(e.target.value)} /></label>
        <label className="record-full">メモ<textarea maxLength={10000} rows={3} value={note} onChange={(e) => setNote(e.target.value)} /></label>
      </div> : mode === 'csv' ? <div className="record-form-grid">
        <p className="record-full">GRCD原本は変更しません。表示データ・記録日時を選択したCSVで置き換えます。</p>
        <label className="record-full">CSV（先頭行は列名・最大32 MiB）<input required type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /></label>
        <label>文字コード<select value={encoding} onChange={(e) => setEncoding(e.target.value)}><option value="utf-8-sig">UTF-8 / UTF-8 BOM</option><option value="cp932">CP932（Shift JIS）</option></select></label>
        <label>日時列名（任意）<input value={timeColumn} maxLength={256} onChange={(e) => setTimeColumn(e.target.value)} /></label>
        <label className="record-full">タイムゾーンのないISO日時の地域<input value={zone} onChange={(e) => setZone(e.target.value)} disabled={!timeColumn} maxLength={100} /></label>
      </div> : <p>「{item.name}」を削除済みにします。原本は保持され、削除済み表示から復帰できます。</p>}
      {error && <p role="alert" className="record-error">{error}</p>}
      <footer><Button type="button" onClick={close} disabled={busy}>キャンセル</Button><Button type="submit" kind={mode === 'delete' ? 'danger' : 'primary'} disabled={busy}>{busy ? '処理中…' : mode === 'delete' ? '削除' : '保存'}</Button></footer>
    </form>
  </Dialog>
}

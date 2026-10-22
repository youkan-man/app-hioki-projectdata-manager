import { useCallback, useEffect, useRef, useState } from 'react'
import { getProjects } from '../api'
import { Button, formatBytes, formatDate } from '../components'
import type { Project } from '../types'
import { ContextMenu, type MenuPosition } from './ContextMenu'
import { RecordDialog } from './RecordDialog'
import { RecordDataView } from './RecordDataView'
import { download, json, query, upload, type RecordFile } from './api'
import './records.css'

type Page = { items: RecordFile[]; total: number }
type Sort = 'started_at' | 'ended_at' | 'created_at' | 'name' | 'size_bytes'

export default function Records() {
  const [projects, setProjects] = useState<Project[]>([])
  const [result, setResult] = useState<Page>({ items: [], total: 0 })
  const [projectId, setProjectId] = useState(''), [search, setSearch] = useState(''), [deleted, setDeleted] = useState(false)
  const [sort, setSort] = useState<Sort>('started_at'), [descending, setDescending] = useState(true), [page, setPage] = useState(0)
  const [nonce, setNonce] = useState(0), [loading, setLoading] = useState(true), [busy, setBusy] = useState(false)
  const [error, setError] = useState(''), [notice, setNotice] = useState('')
  const [selected, setSelected] = useState<RecordFile | null>(null)
  const [menu, setMenu] = useState<{ item: RecordFile; position: MenuPosition } | null>(null)
  const [dialog, setDialog] = useState<{ item: RecordFile; mode: 'edit' | 'csv' | 'delete' } | null>(null)
  const input = useRef<HTMLInputElement>(null)
  const closeMenu = useCallback(() => setMenu(null), [])
  const filters = query({ project_id: projectId && projectId !== 'unlinked' ? projectId : undefined, unlinked: projectId === 'unlinked', search, include_deleted: deleted, sort, descending, offset: page * 50 })

  useEffect(() => {
    let active = true
    void getProjects(true).then((items) => { if (active) setProjects(items) }).catch((e: Error) => { if (active) setError(e.message) })
    return () => { active = false }
  }, [nonce])
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError(''); setMenu(null)
    const timer = setTimeout(() => {
      void json<Page>(`?${filters}`, { signal: controller.signal }).then((data) => {
        setResult(data)
        if (page > 0 && !data.items.length) setPage(Math.max(0, Math.ceil(data.total / 50) - 1))
      }).catch((e: Error) => { if (e.name !== 'AbortError') setError(e.message) }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    }, 150)
    return () => { clearTimeout(timer); controller.abort() }
  }, [filters, nonce, page])

  async function refresh() {
    setNonce((value) => value + 1)
    if (selected) setSelected(await json<RecordFile>(`/${selected.id}`))
  }
  function run(action: () => Promise<void>) {
    setBusy(true); setError('')
    void action().catch((e: Error) => setError(e.message)).finally(() => setBusy(false))
  }
  function openMenu(item: RecordFile, trigger: HTMLElement, x?: number, y?: number) {
    const rectangle = trigger.getBoundingClientRect()
    setMenu({ item, position: { trigger, x: x ?? rectangle.right, y: y ?? rectangle.bottom } })
  }
  function changeSort(value: Sort) { setDescending(sort === value ? !descending : true); setSort(value); setPage(0) }
  const localeZone = Intl.DateTimeFormat().resolvedOptions().timeZone
  return <div className="app-shell records-shell">
    <header className="topbar"><div className="brand"><span className="brand-mark">H</span><strong>GENNECT Record Manager</strong></div><span>{result.total.toLocaleString()} 件</span></header>
    <main>
      <div className="record-page-heading"><h1>レコードデータ</h1><span>日時表示: {localeZone}</span></div>
      <section className="panel" aria-label="レコード一覧">
        <div className="record-toolbar">
          <Button kind="primary" icon="add" disabled={busy} onClick={() => input.current?.click()}>GRCDを登録</Button>
          <input ref={input} type="file" accept=".grcd" multiple hidden aria-label="GRCDファイル" onChange={(event) => {
            const files = Array.from(event.target.files ?? []); event.target.value = ''
            if (!files.length) return
            run(async () => {
              if (files.length > 20) throw new Error('一度に登録できるファイルは20件までです。')
              let added = 0, duplicate = 0, unlinked = 0
              const failed: string[] = []
              for (const file of files) {
                try {
                  setNotice(`登録中: ${file.name}`)
                  const response = await upload(file, projectId === 'unlinked' ? '' : projectId)
                  response.duplicate ? duplicate++ : added++
                  if (!response.record.project_id) unlinked++
                } catch (e) { failed.push(`${file.name}: ${e instanceof Error ? e.message : '登録失敗'}`) }
              }
              setNotice(`${added} 件登録、${duplicate} 件は同一原本が登録済み${unlinked ? `、${unlinked} 件は未関連付け` : ''}${failed.length ? `、${failed.length} 件失敗` : ''}`)
              await refresh()
              if (failed.length) setError(failed.join(' / '))
            })
          }} />
          <label>プロジェクト<select value={projectId} disabled={busy} onChange={(e) => { setProjectId(e.target.value); setPage(0) }}><option value="">すべて / 登録時は同名を照合</option><option value="unlinked">未関連付け</option>{projects.map((p) => <option key={p.id} value={p.id}>{p.displayName}{p.deletedAt ? '（削除済み）' : ''} · {p.sourceUuid.slice(0, 8)}</option>)}</select></label>
          <label>検索<input type="search" value={search} maxLength={255} onChange={(e) => { setSearch(e.target.value); setPage(0) }} placeholder="記録名・ファイル名・メモ" /></label>
          <Button icon="refresh" disabled={busy || loading} onClick={() => run(refresh)}>更新</Button>
        </div>
        <div className="record-toolbar">
          <label>並べ替え<select value={sort} onChange={(e) => { setSort(e.target.value as Sort); setPage(0) }}><option value="started_at">記録開始</option><option value="ended_at">記録終了</option><option value="created_at">登録日時</option><option value="name">記録名</option><option value="size_bytes">サイズ</option></select></label>
          <Button onClick={() => { setDescending(!descending); setPage(0) }}>{descending ? '降順 ▼' : '昇順 ▲'}</Button>
          <label className="record-check"><input type="checkbox" checked={deleted} onChange={(e) => { setDeleted(e.target.checked); setPage(0) }} />削除済みを含める</label>
        </div>
        {notice && <p role="status" className="record-notice">{notice}</p>}
        {error && <p role="alert" className="record-error">{error}</p>}
        <div className="record-grid" aria-busy={loading}>
          {loading ? <p role="status">記録を読み込み中…</p> : result.items.length ? <table className="record-list"><thead><tr><th><button onClick={() => changeSort('name')}>記録名</button></th><th>プロジェクト</th><th aria-sort={sort === 'started_at' ? descending ? 'descending' : 'ascending' : 'none'}><button onClick={() => changeSort('started_at')}>記録開始</button></th><th aria-sort={sort === 'ended_at' ? descending ? 'descending' : 'ascending' : 'none'}><button onClick={() => changeSort('ended_at')}>記録終了</button></th><th>記録時間</th><th>サイズ</th><th>解析 / 状態</th><th>操作</th></tr></thead><tbody>{result.items.map((item) => <tr key={item.id} className={`${item.deleted_at ? 'deleted-row' : ''} ${selected?.id === item.id ? 'record-selected' : ''}`} tabIndex={0} onContextMenu={(e) => { e.preventDefault(); openMenu(item, e.currentTarget, e.clientX, e.clientY) }} onKeyDown={(e) => {
            if (e.key === 'ContextMenu' || (e.shiftKey && e.key === 'F10')) { e.preventDefault(); openMenu(item, e.currentTarget) }
            else if (e.key === 'Enter' && e.target === e.currentTarget) setSelected(item)
          }}><td className="record-name">{item.name}</td><td>{item.project_name ?? '未関連付け'}{item.project_deleted ? '（削除済み）' : ''}</td><td>{item.started_at ? formatDate(item.started_at) : '不明'}</td><td>{item.ended_at ? formatDate(item.ended_at) : '不明'}</td><td>{item.duration_seconds === null ? '—' : `${item.duration_seconds.toLocaleString(undefined, { maximumFractionDigits: 3 })} 秒`}</td><td>{formatBytes(item.size_bytes)}</td><td>{item.deleted_at ? '削除済み' : item.inspection.status === 'ready' ? item.has_companion_csv ? '関連付けCSV' : `${item.inspection.tables.length} 表` : '原本のみ'}</td><td><button className="record-menu-button" aria-haspopup="menu" aria-label={`${item.name} の操作`} disabled={busy} onClick={(e) => openMenu(item, e.currentTarget)}>⋯</button></td></tr>)}</tbody></table> : <p>該当する記録はありません。</p>}
        </div>
        <div className="record-pagination"><Button disabled={page === 0 || loading} onClick={() => setPage(page - 1)}>前へ</Button><span>{result.total ? page * 50 + 1 : 0}–{Math.min((page + 1) * 50, result.total)} / {result.total.toLocaleString()} 件</span><Button disabled={(page + 1) * 50 >= result.total || loading} onClick={() => setPage(page + 1)}>次へ</Button></div>
      </section>
      {selected && <RecordDataView key={selected.id} item={selected} onClose={() => setSelected(null)} />}
    </main>
    {menu && <ContextMenu position={menu.position} onClose={closeMenu} actions={[
      { label: 'データを開く', run: () => setSelected(menu.item) },
      { label: '編集・プロジェクト関連付け', disabled: !!menu.item.deleted_at, run: () => setDialog({ item: menu.item, mode: 'edit' }) },
      { label: 'CSVを関連付け', disabled: !!menu.item.deleted_at, run: () => setDialog({ item: menu.item, mode: 'csv' }) },
      { label: 'GRCD原本をダウンロード', run: () => run(() => download(`/${menu.item.id}/original`, menu.item.filename)) },
      { label: '最初の表をCSV出力', disabled: !menu.item.inspection.tables.length, run: () => run(() => download(`/${menu.item.id}/tables/0/csv`, `${menu.item.name}.csv`)) },
      ...(menu.item.has_companion_csv ? [{ label: '関連付けCSV原本をダウンロード', run: () => run(() => download(`/${menu.item.id}/companion-csv/original`, `${menu.item.name}.csv`)) }] : []),
      menu.item.deleted_at ? { label: '削除済みから復帰', run: () => run(async () => { await json(`/${menu.item.id}/restore?revision=${menu.item.revision}`, { method: 'POST' }); await refresh() }) } : { label: '削除', danger: true, run: () => setDialog({ item: menu.item, mode: 'delete' }) },
    ]} />}
    {dialog && <RecordDialog item={dialog.item} projects={projects} mode={dialog.mode} onClose={() => setDialog(null)} onSaved={refresh} />}
  </div>
}

import { useCallback, useEffect, useMemo, useState } from 'react'
import { createCanonicalArchive, createCanonicalArchiveFromFiles, validateCanonicalArchive } from './archive'
import * as api from './api'
import { Button, EmptyState, formatBytes, formatDate, Icon, Modal, Spinner } from './components'
import { chooseDirectory, ensurePermission, getDirectoryHandle, restoreArchiveToDirectory, scanProjects, supportsFileSystemAccess, triggerDownload } from './fileSystem'
import type { DiscoveredProject, ModalState, Project, RestoreTarget } from './types'
import './styles.css'

type Notice = { kind: 'success' | 'error' | 'info'; message: string } | null

export default function App() {
  const [projects, setProjects] = useState<Project[]>([])
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [modal, setModal] = useState<ModalState>({ kind: 'closed' })
  const [includeDeleted, setIncludeDeleted] = useState(false)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState<Notice>(null)
  const [directoryName, setDirectoryName] = useState<string | null>(null)
  const [restoreTarget, setRestoreTarget] = useState<RestoreTarget | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    try { setProjects(await api.getProjects(includeDeleted)) }
    catch (error) { setNotice({ kind: 'error', message: error instanceof Error ? error.message : '一覧を取得できませんでした。' }) }
    finally { setLoading(false) }
  }, [includeDeleted])

  useEffect(() => { void load() }, [load])
  useEffect(() => { void getDirectoryHandle().then((handle) => setDirectoryName(handle?.name ?? null)).catch(() => undefined) }, [])
  useEffect(() => { if (!notice) return; const id = setTimeout(() => setNotice(null), 5500); return () => clearTimeout(id) }, [notice])

  async function run(action: () => Promise<void>, success: string) {
    setBusy(true)
    try { await action(); setNotice({ kind: 'success', message: success }); setModal({ kind: 'closed' }); await load() }
    catch (error) { setNotice({ kind: 'error', message: error instanceof Error ? error.message : '操作に失敗しました。' }) }
    finally { setBusy(false) }
  }

  async function restoreVersion(target: RestoreTarget) {
    setBusy(true)
    try {
      const archive = await api.downloadArchive(target.project.id, target.version.id)
      if (!supportsFileSystemAccess) {
        triggerDownload(archive, `${target.project.sourceUuid}-v${target.version.version}.zip`)
        setNotice({ kind: 'info', message: 'ZIPをダウンロードしました。GENNECT Spaceのデータフォルダーへ手動で展開してください。' })
        return
      }
      const root = await getDirectoryHandle()
      if (!root) throw new Error('先に設定からGENNECT Spaceのdataフォルダーを選択してください。')
      if (!await ensurePermission(root, true)) throw new Error('フォルダーへの書き込みが許可されませんでした。')
      const result = await restoreArchiveToDirectory(root, archive, target.project.sourceUuid)
      if (result !== 'cancelled') setNotice({ kind: 'success', message: `バージョン ${target.version.version} を${result === 'overwritten' ? '上書き' : '復元'}しました。` })
    } catch (error) { setNotice({ kind: 'error', message: error instanceof Error ? error.message : '復元に失敗しました。' }) }
    finally { setBusy(false); setRestoreTarget(null) }
  }

  const activeCount = useMemo(() => projects.filter((project) => !project.deletedAt).length, [projects])
  return <div className="app-shell">
    <header className="topbar"><div className="brand"><span className="brand-mark">H</span><span><strong>GENNECT Project Manager</strong><small>Hioki GENNECT Space</small></span></div><div className="header-meta"><span className="status-dot" />API 接続済み <span className="divider" /> {activeCount} プロジェクト</div></header>
    <main>
      <div className="page-heading"><div><p className="breadcrumb">ホーム / プロジェクト</p><h1>プロジェクト データ</h1><p>GENNECT Space のデータを保存し、必要なバージョンを端末へ呼び出します。</p></div></div>
      {!supportsFileSystemAccess && <div className="banner warning"><strong>フォルダー連携は利用できません</strong><span>Chrome / Edge を使用してください。このブラウザーではZIPのアップロードとダウンロードのみ利用できます。</span></div>}
      <section className="panel">
        <div className="command-bar"><div><Button kind="primary" icon="add" onClick={() => setModal({ kind: 'register' })}>プロジェクトを登録</Button><Button icon="refresh" onClick={() => void load()} disabled={loading}>更新</Button></div><div><span className="directory-chip"><Icon name="folder" />{directoryName ?? 'フォルダー未設定'}</span><Button icon="settings" onClick={() => setModal({ kind: 'settings' })}>設定</Button></div></div>
        {loading ? <div className="loading-area"><Spinner label="プロジェクトを読み込んでいます" /></div> : projects.length === 0 ? <EmptyState title="プロジェクトはまだありません" description="GENNECT Space のdataフォルダー、またはZIPファイルから最初のプロジェクトを登録してください。" action={<Button kind="primary" icon="add" onClick={() => setModal({ kind: 'register' })}>登録を開始</Button>} /> :
          <div className="table-wrap"><table><thead><tr><th className="expand-cell" /><th>プロジェクト</th><th>UUID</th><th>最新バージョン</th><th>更新日時</th><th>状態</th><th className="actions-cell">操作</th></tr></thead><tbody>{projects.map((project) => {
            const open = expanded.has(project.id); const latest = project.versions[0]
            return <ProjectRows key={project.id} project={project} open={open} latest={latest} onToggle={() => setExpanded((current) => { const next = new Set(current); next.has(project.id) ? next.delete(project.id) : next.add(project.id); return next })} onEdit={() => setModal({ kind: 'edit', project })} onDelete={() => setModal({ kind: 'delete', project })} onRestoreRecord={() => setModal({ kind: 'restore-record', project })} onRestoreVersion={(version) => setRestoreTarget({ project, version })} onDownload={async (version) => { try { const blob = await api.downloadArchive(project.id, version.id); triggerDownload(blob, `${project.sourceUuid}-v${version.version}.zip`) } catch (error) { setNotice({ kind: 'error', message: error instanceof Error ? error.message : 'ダウンロードに失敗しました。' }) } }} />
          })}</tbody></table></div>}
      </section>
    </main>
    {notice && <div className={`toast ${notice.kind}`} role="status">{notice.message}<button onClick={() => setNotice(null)} aria-label="通知を閉じる"><Icon name="close" /></button></div>}
    {modal.kind === 'register' && <RegisterModal busy={busy} onClose={() => setModal({ kind: 'closed' })} onDirectoryChanged={setDirectoryName} importAction={async (input) => { setBusy(true); try { await api.importProject(input); setNotice({ kind: 'success', message: 'プロジェクトを登録しました。' }); setModal({ kind: 'closed' }); await load() } catch (error) { setNotice({ kind: 'error', message: error instanceof Error ? error.message : '登録に失敗しました。' }) } finally { setBusy(false) } }} />}
    {modal.kind === 'edit' && <EditModal project={modal.project} busy={busy} onClose={() => setModal({ kind: 'closed' })} onSave={(values) => void run(() => api.updateProject(modal.project.id, values), 'プロジェクト情報を更新しました。')} />}
    {modal.kind === 'delete' && <ConfirmModal title="プロジェクトを削除" message={`「${modal.project.displayName}」を一覧から削除します。保存ファイルは保持され、設定から削除済みを表示すると復帰できます。`} confirmLabel="削除" danger busy={busy} onClose={() => setModal({ kind: 'closed' })} onConfirm={() => void run(() => api.deleteProject(modal.project.id), 'プロジェクトを削除済みにしました。')} />}
    {modal.kind === 'restore-record' && <ConfirmModal title="削除済みレコードを復帰" message={`「${modal.project.displayName}」をプロジェクト一覧へ戻します。`} confirmLabel="復帰" busy={busy} onClose={() => setModal({ kind: 'closed' })} onConfirm={() => void run(() => api.restoreDeletedProject(modal.project.id), 'プロジェクトを復帰しました。')} />}
    {modal.kind === 'settings' && <SettingsModal includeDeleted={includeDeleted} directoryName={directoryName} onClose={() => setModal({ kind: 'closed' })} onIncludeDeleted={setIncludeDeleted} onDirectoryChanged={setDirectoryName} />}
    {restoreTarget && <ConfirmModal title="バージョンを呼び出す" message={supportsFileSystemAccess ? `バージョン ${restoreTarget.version.version} を「${directoryName ?? '未設定'}」へ展開します。既存の同一UUIDフォルダーがある場合は、続ける前に上書きを確認します。` : `バージョン ${restoreTarget.version.version} をZIPとしてダウンロードします。`} confirmLabel={supportsFileSystemAccess ? '呼び出す' : 'ダウンロード'} busy={busy} onClose={() => setRestoreTarget(null)} onConfirm={() => void restoreVersion(restoreTarget)} />}
  </div>
}

function ProjectRows({ project, latest, open, onToggle, onEdit, onDelete, onRestoreRecord, onRestoreVersion, onDownload }: { project: Project; latest: Project['versions'][number] | undefined; open: boolean; onToggle: () => void; onEdit: () => void; onDelete: () => void; onRestoreRecord: () => void; onRestoreVersion: (version: Project['versions'][number]) => void; onDownload: (version: Project['versions'][number]) => void }) {
  return <><tr className={project.deletedAt ? 'deleted-row' : ''}><td className="expand-cell"><button className={`chevron ${open ? 'open' : ''}`} onClick={onToggle} aria-label="バージョン履歴を展開"><Icon name="chevron" /></button></td><td><strong>{project.displayName}</strong>{project.projectName !== project.displayName && <small className="subtext">{project.projectName}</small>}{project.note && <small className="subtext">{project.note}</small>}</td><td><code>{project.sourceUuid}</code></td><td>{latest ? `v${latest.version}` : '—'}<small className="subtext">{project.versions.length} 件</small></td><td>{formatDate(project.updatedAt)}</td><td><span className={`badge ${project.deletedAt ? 'deleted' : 'active'}`}>{project.deletedAt ? '削除済み' : '利用可能'}</span></td><td className="actions-cell">{project.deletedAt ? <Button icon="restore" onClick={onRestoreRecord}>復帰</Button> : <><button className="table-action" onClick={onEdit} title="編集"><Icon name="edit" /></button><button className="table-action danger-text" onClick={onDelete} title="削除"><Icon name="delete" /></button></>}</td></tr>
    {open && <tr className="version-container"><td /><td colSpan={6}>{project.versions.length === 0 ? <p className="no-versions">バージョン履歴はありません。</p> : <div className="version-list"><div className="version-heading"><span>バージョン</span><span>保存日時</span><span>サイズ</span><span>メモ</span><span /></div>{project.versions.map((version) => <div className="version-row" key={version.id}><strong>v{version.version}</strong><span>{formatDate(version.createdAt)}</span><span>{formatBytes(version.archiveSize)}</span><span>{version.note || '—'}</span><span className="version-actions"><button onClick={() => onDownload(version)} title="ZIPをダウンロード"><Icon name="download" /></button>{!project.deletedAt && <button onClick={() => onRestoreVersion(version)} title="このバージョンを呼び出す"><Icon name="restore" /></button>}</span></div>)}</div>}</td></tr>}
  </>
}

function RegisterModal({ busy, onClose, onDirectoryChanged, importAction }: { busy: boolean; onClose: () => void; onDirectoryChanged: (name: string) => void; importAction: (input: Parameters<typeof api.importProject>[0]) => Promise<void> }) {
  const [tab, setTab] = useState<'directory' | 'zip'>(supportsFileSystemAccess ? 'directory' : 'zip'); const [found, setFound] = useState<DiscoveredProject[]>([]); const [scanning, setScanning] = useState(false); const [scanMessage, setScanMessage] = useState(''); const [note, setNote] = useState('')
  const scan = useCallback(async (choose = false) => { setScanning(true); setScanMessage(''); try { const root = choose ? await chooseDirectory() : await getDirectoryHandle(); if (!root) { setScanMessage('初回はGENNECT Spaceのdataフォルダーを選択してください。'); return } onDirectoryChanged(root.name); if (!await ensurePermission(root)) { setScanMessage('フォルダーの読み取り許可が必要です。'); return } const result = await scanProjects(root); setFound(result); if (!result.length) setScanMessage('UUIDフォルダー内に *.gprj が見つかりませんでした。') } catch (error) { if (error instanceof DOMException && error.name === 'AbortError') return; setScanMessage(error instanceof Error ? error.message : '検索に失敗しました。') } finally { setScanning(false) } }, [onDirectoryChanged])
  useEffect(() => { if (supportsFileSystemAccess) void scan(false) }, [scan])
  async function uploadDirectory(project: DiscoveredProject) { const blob = await createCanonicalArchive(project.sourceUuid, project.directory); await importAction({ archive: blob, fileName: `${project.sourceUuid}.zip`, sourceUuid: project.sourceUuid, projectName: project.projectName, note }) }
  async function uploadZip(file: File) { setScanMessage(''); try { const valid = validateCanonicalArchive(new Uint8Array(await file.arrayBuffer())); const gprj = valid.files.find((item) => item.relativePath.length === 1 && item.relativePath[0]?.toLowerCase().endsWith('.gprj')); const name = gprj?.relativePath[0]?.replace(/\.gprj$/i, '') ?? file.name.replace(/\.zip$/i, ''); await importAction({ archive: file, fileName: file.name, sourceUuid: valid.rootUuid, projectName: name, note }) } catch (error) { setScanMessage(error instanceof Error ? error.message : 'ZIPを読み取れませんでした。') } }
  async function uploadSelectedDirectory(fileList: FileList) { setScanMessage(''); try { const selected = await createCanonicalArchiveFromFiles(fileList); await importAction({ archive: selected.archive, fileName: selected.fileName, sourceUuid: selected.sourceUuid, projectName: selected.projectName, note }) } catch (error) { setScanMessage(error instanceof Error ? error.message : 'ディレクトリを読み取れませんでした。') } }
  return <Modal title="プロジェクトを登録" subtitle="GENNECT Spaceのデータフォルダー、保存済みZIP、またはプロジェクトディレクトリから登録します。" onClose={onClose} width="760px"><div className="tabs"><button className={tab === 'directory' ? 'active' : ''} onClick={() => { setScanMessage(''); setTab('directory') }} disabled={!supportsFileSystemAccess}><Icon name="folder" />保存場所から検索</button><button className={tab === 'zip' ? 'active' : ''} onClick={() => { setScanMessage(''); setTab('zip') }}><Icon name="zip" />ファイルから登録</button></div><label className="field"><span>バージョンメモ（任意）</span><input value={note} onChange={(event) => setNote(event.target.value)} placeholder="例: 計測条件を更新" /></label>{scanMessage && <div className="inline-message">{scanMessage}</div>}{tab === 'directory' ? <div><div className="scan-toolbar"><span>{found.length ? `${found.length} 件のプロジェクト` : '保存元フォルダーを検索します'}</span><Button icon="folder" onClick={() => void scan(true)} disabled={scanning}>{scanning ? '検索中…' : found.length ? 'フォルダーを変更' : 'フォルダーを選択'}</Button></div>{scanning ? <div className="loading-area small"><Spinner label="UUIDフォルダーを検索中" /></div> : <div className="discovered-list">{found.map((project) => <div className="discovered-item" key={project.sourceUuid}><span className="file-tile"><Icon name="folder" /></span><span><strong>{project.projectName}</strong><small>{project.gprjFileName} · {project.sourceUuid}</small></span><Button kind="primary" onClick={() => void uploadDirectory(project)} disabled={busy}>{busy ? '登録中…' : '登録'}</Button></div>)}</div>}</div> : <div className="local-import-options"><label className="import-option"><span className="import-option-icon"><Icon name="zip" /></span><span><strong>ZIPファイル</strong><small>保存済みの正規形式ZIPをそのまま登録します。</small><span className="file-picker-label">ZIPを選択</span></span><input type="file" accept=".zip,application/zip" disabled={busy} onChange={(event) => { const file = event.target.files?.[0]; if (file) void uploadZip(file); event.currentTarget.value = '' }} /></label><div className="option-separator"><span>または</span></div><label className="import-option"><span className="import-option-icon"><Icon name="folder" /></span><span><strong>プロジェクトディレクトリ</strong><small>UUID名のフォルダーを選択し、ブラウザー上でZIP化して登録します。</small><span className="file-picker-label">ディレクトリを選択</span></span><input type="file" webkitdirectory="" directory="" multiple disabled={busy} onChange={(event) => { const files = event.target.files; if (files?.length) void uploadSelectedDirectory(files); event.currentTarget.value = '' }} /></label><p className="import-requirement">どちらも最上位にUUIDフォルダーが1つあり、その直下に *.gprj が1つ必要です。</p></div>}</Modal>
}

function EditModal({ project, busy, onClose, onSave }: { project: Project; busy: boolean; onClose: () => void; onSave: (values: { displayName: string; note: string }) => void }) { const [displayName, setDisplayName] = useState(project.displayName); const [note, setNote] = useState(project.note); return <Modal title="プロジェクト情報を編集" onClose={onClose} footer={<><Button onClick={onClose}>キャンセル</Button><Button kind="primary" disabled={busy || !displayName.trim()} onClick={() => onSave({ displayName: displayName.trim(), note: note.trim() })}>{busy ? '保存中…' : '保存'}</Button></>}><label className="field"><span>表示名</span><input autoFocus value={displayName} onChange={(event) => setDisplayName(event.target.value)} /></label><label className="field"><span>メモ</span><textarea rows={4} value={note} onChange={(event) => setNote(event.target.value)} /></label></Modal> }

function ConfirmModal({ title, message, confirmLabel, danger, busy, onClose, onConfirm }: { title: string; message: string; confirmLabel: string; danger?: boolean; busy: boolean; onClose: () => void; onConfirm: () => void }) { return <Modal title={title} onClose={onClose} footer={<><Button onClick={onClose}>キャンセル</Button><Button kind={danger ? 'danger' : 'primary'} disabled={busy} onClick={onConfirm}>{busy ? '処理中…' : confirmLabel}</Button></>}><p className="confirm-message">{message}</p></Modal> }

function SettingsModal({ includeDeleted, directoryName, onClose, onIncludeDeleted, onDirectoryChanged }: { includeDeleted: boolean; directoryName: string | null; onClose: () => void; onIncludeDeleted: (value: boolean) => void; onDirectoryChanged: (name: string) => void }) { const [message, setMessage] = useState(''); async function pick() { try { const handle = await chooseDirectory(); onDirectoryChanged(handle.name); setMessage('フォルダーを保存しました。') } catch (error) { if (!(error instanceof DOMException && error.name === 'AbortError')) setMessage(error instanceof Error ? error.message : '選択できませんでした。') } } return <Modal title="設定" subtitle="このブラウザーに保存される端末固有の設定です。" onClose={onClose} footer={<Button kind="primary" onClick={onClose}>完了</Button>}><div className="setting-row"><div><strong>GENNECT Space dataフォルダー</strong><p>通常は %APPDATA%\gennect-space\data です。</p><code>{directoryName ?? '未設定'}</code></div><Button icon="folder" disabled={!supportsFileSystemAccess} onClick={() => void pick()}>変更</Button></div><div className="setting-row"><div><strong>削除済みプロジェクト</strong><p>論理削除されたレコードを一覧に表示します。</p></div><label className="switch"><input type="checkbox" checked={includeDeleted} onChange={(event) => onIncludeDeleted(event.target.checked)} /><span /></label></div>{message && <div className="inline-message success">{message}</div>}</Modal> }

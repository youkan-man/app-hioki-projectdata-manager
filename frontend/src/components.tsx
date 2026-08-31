import type { PropsWithChildren, ReactNode } from 'react'

export function Icon({ name }: { name: 'add' | 'settings' | 'refresh' | 'edit' | 'delete' | 'restore' | 'folder' | 'zip' | 'chevron' | 'download' | 'close' }) {
  const paths: Record<typeof name, ReactNode> = {
    add: <><path d="M12 5v14M5 12h14" /></>, settings: <><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-1.6v-.2h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z" /></>,
    refresh: <><path d="M20 11a8 8 0 1 0-2.3 5.7" /><path d="M20 4v7h-7" /></>, edit: <><path d="m14 4 6 6L9 21H3v-6Z" /><path d="m12 6 6 6" /></>,
    delete: <><path d="M4 7h16M9 7V4h6v3m3 0-1 14H7L6 7M10 11v6m4-6v6" /></>, restore: <><path d="M4 12a8 8 0 1 0 2.3-5.7L4 8.6" /><path d="M4 3v5.6h5.6" /></>,
    folder: <path d="M3 6h7l2 2h9v12H3Z" />, zip: <><path d="M6 2h9l3 3v17H6Z" /><path d="M11 2v3h2V8h-2v3h2v3h-2v3h2" /></>, chevron: <path d="m8 10 4 4 4-4" />, download: <><path d="M12 3v13m-5-5 5 5 5-5" /><path d="M4 20h16" /></>, close: <path d="m6 6 12 12M18 6 6 18" />,
  }
  return <svg className="icon" viewBox="0 0 24 24" aria-hidden="true">{paths[name]}</svg>
}

export function Button({ children, icon, kind = 'secondary', ...props }: PropsWithChildren<{ icon?: Parameters<typeof Icon>[0]['name']; kind?: 'primary' | 'secondary' | 'danger' } & React.ButtonHTMLAttributes<HTMLButtonElement>>) {
  return <button className={`button ${kind}`} {...props}>{icon && <Icon name={icon} />}{children}</button>
}

export function Modal({ title, subtitle, onClose, children, footer, width = '640px' }: PropsWithChildren<{ title: string; subtitle?: string; onClose: () => void; footer?: ReactNode; width?: string }>) {
  return <div className="modal-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
    <section className="modal" role="dialog" aria-modal="true" aria-labelledby="modal-title" style={{ maxWidth: width }}>
      <header className="modal-header"><div><h2 id="modal-title">{title}</h2>{subtitle && <p>{subtitle}</p>}</div><button className="icon-button" onClick={onClose} aria-label="閉じる"><Icon name="close" /></button></header>
      <div className="modal-body">{children}</div>{footer && <footer className="modal-footer">{footer}</footer>}
    </section>
  </div>
}

export function Spinner({ label = '読み込み中' }: { label?: string }) { return <span className="spinner-wrap"><span className="spinner" />{label}</span> }

export function EmptyState({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return <div className="empty-state"><div className="empty-icon"><Icon name="folder" /></div><h3>{title}</h3><p>{description}</p>{action}</div>
}

export function formatDate(value: string): string {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('ja-JP', { dateStyle: 'medium', timeStyle: 'short' }).format(date)
}

export function formatBytes(value: number): string {
  if (!value) return '—'
  const units = ['B', 'KB', 'MB', 'GB']; let size = value; let unit = 0
  while (size >= 1024 && unit < units.length - 1) { size /= 1024; unit++ }
  return `${size.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`
}

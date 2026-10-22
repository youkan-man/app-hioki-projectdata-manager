export type TableInfo = { index: number; name: string; columns: string[]; row_count: number; time_column: string | null }
export type RecordFile = {
  id: string; project_id: string | null; project_name: string | null; project_deleted: boolean;
  filename: string; name: string; note: string; sha256: string; size_bytes: number;
  started_at: string | null; ended_at: string | null; duration_seconds: number | null;
  time_source: string; created_at: string; deleted_at: string | null; revision: number;
  has_companion_csv: boolean;
  inspection: { format: string; status: 'ready' | 'unavailable'; message: string; tables: TableInfo[]; warnings: string[] }
}
export type RowPage = { columns: string[]; rows: string[][]; total: number; offset: number }
const BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') ?? ''
export async function request(path: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(`${BASE}/api/records${path}`, init)
  if (!response.ok) {
    let message = `記録APIエラー (${response.status})`
    try {
      const body = await response.json() as { detail?: unknown }
      if (typeof body.detail === 'string') message = body.detail
      else if (Array.isArray(body.detail)) message = body.detail.map((e: { msg?: string }) => e.msg ?? '').filter(Boolean).join(' / ') || message
    } catch { /* retain HTTP status when the response is not JSON */ }
    throw new Error(message)
  }
  return response
}
export async function json<T>(path: string, init?: RequestInit): Promise<T> {
  return await (await request(path, init)).json() as T
}
export async function upload(file: File, projectId: string) {
  const form = new FormData(); form.append('record', file)
  if (projectId) form.append('project_id', projectId)
  return json<{ record: RecordFile; duplicate: boolean; association_candidates: { id: string; name: string }[] }>('/import', { method: 'POST', body: form })
}
export function query(values: Record<string, string | number | boolean | undefined>): string {
  const params = new URLSearchParams()
  Object.entries(values).forEach(([key, value]) => { if (value !== undefined && value !== '') params.set(key, String(value)) })
  return params.toString()
}
export async function download(path: string, filename: string) {
  const blob = await (await request(path)).blob()
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a'); anchor.href = url; anchor.download = filename
  document.body.append(anchor); anchor.click(); anchor.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

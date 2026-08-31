import type { Project, ProjectId, ProjectVersion, VersionId } from './types'

const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') ?? ''

function text(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : fallback
}

function number(value: unknown, fallback = 0): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback
}

function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('API応答の形式が不正です。')
  return value as Record<string, unknown>
}

function parseVersion(input: unknown, projectUuid: string): ProjectVersion {
  const item = record(input)
  return {
    id: text(item.id ?? item.version_id) as VersionId,
    version: number(item.version ?? item.version_number),
    sourceUuid: text(item.source_uuid, projectUuid),
    archiveSize: number(item.archive_size ?? item.size_bytes),
    note: text(item.note),
    createdAt: text(item.created_at),
  }
}

function parseProject(input: unknown): Project {
  const item = record(input)
  const sourceUuid = text(item.source_uuid)
  const rawVersions = Array.isArray(item.versions) ? item.versions : []
  const projectName = text(item.project_name ?? item.name)
  return {
    id: text(item.id) as ProjectId,
    sourceUuid,
    projectName,
    displayName: text(item.display_name ?? item.name, projectName),
    note: text(item.description ?? item.note),
    createdAt: text(item.created_at),
    updatedAt: text(item.updated_at),
    deletedAt: item.deleted_at === null || item.deleted_at === undefined ? null : text(item.deleted_at),
    versions: rawVersions.map((version) => parseVersion(version, sourceUuid)).sort((a, b) => b.version - a.version),
  }
}

async function request(path: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(`${API_BASE}${path}`, init)
  if (!response.ok) {
    let message = `APIエラー (${response.status})`
    try {
      const body = record(await response.json())
      message = text(body.message ?? body.detail ?? body.error, message)
    } catch { /* preserve status message */ }
    throw new Error(message)
  }
  return response
}

export async function getProjects(includeDeleted: boolean): Promise<Project[]> {
  const response = await request(`/api/projects?include_deleted=${includeDeleted}`)
  const body: unknown = await response.json()
  const items = Array.isArray(body) ? body : record(body).items ?? record(body).projects
  if (!Array.isArray(items)) throw new Error('プロジェクト一覧の形式が不正です。')
  return items.map(parseProject)
}

export async function importProject(input: {
  archive: Blob
  fileName: string
  sourceUuid: string
  projectName: string
  note: string
}): Promise<void> {
  const form = new FormData()
  form.append('archive', input.archive, input.fileName)
  form.append('source_uuid', input.sourceUuid)
  form.append('project_name', input.projectName)
  form.append('note', input.note)
  await request('/api/projects/import', { method: 'POST', body: form })
}

export async function updateProject(id: ProjectId, values: { displayName: string; note: string }): Promise<void> {
  await request(`/api/projects/${encodeURIComponent(id)}`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: values.displayName, description: values.note }),
  })
}

export async function deleteProject(id: ProjectId): Promise<void> {
  await request(`/api/projects/${encodeURIComponent(id)}`, { method: 'DELETE' })
}

export async function restoreDeletedProject(id: ProjectId): Promise<void> {
  await request(`/api/projects/${encodeURIComponent(id)}/restore`, { method: 'POST' })
}

export async function downloadArchive(projectId: ProjectId, versionId: VersionId): Promise<Blob> {
  const response = await request(`/api/projects/${encodeURIComponent(projectId)}/versions/${encodeURIComponent(versionId)}/archive`)
  return response.blob()
}

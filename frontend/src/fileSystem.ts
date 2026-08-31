import type { DiscoveredProject } from './types'
import { UUID_PATTERN, validateCanonicalArchive } from './archive'

const DB_NAME = 'gennect-project-manager'
const STORE_NAME = 'settings'
const DIRECTORY_KEY = 'gennect-data-directory'

export const supportsFileSystemAccess = typeof window !== 'undefined' && typeof window.showDirectoryPicker === 'function'

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 1)
    request.onupgradeneeded = () => request.result.createObjectStore(STORE_NAME)
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

export async function saveDirectoryHandle(handle: FileSystemDirectoryHandle): Promise<void> {
  const db = await openDatabase()
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, 'readwrite')
    tx.objectStore(STORE_NAME).put(handle, DIRECTORY_KEY)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
  db.close()
}

export async function getDirectoryHandle(): Promise<FileSystemDirectoryHandle | null> {
  if (!supportsFileSystemAccess) return null
  const db = await openDatabase()
  const value = await new Promise<unknown>((resolve, reject) => {
    const request = db.transaction(STORE_NAME).objectStore(STORE_NAME).get(DIRECTORY_KEY)
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
  db.close()
  return value && typeof value === 'object' && 'kind' in value && value.kind === 'directory' ? value as FileSystemDirectoryHandle : null
}

export async function chooseDirectory(): Promise<FileSystemDirectoryHandle> {
  if (!window.showDirectoryPicker) throw new Error('このブラウザーはフォルダーアクセスに対応していません。')
  const handle = await window.showDirectoryPicker({ mode: 'readwrite' })
  await saveDirectoryHandle(handle)
  return handle
}

export async function ensurePermission(handle: FileSystemDirectoryHandle, write = false): Promise<boolean> {
  const descriptor: FileSystemHandlePermissionDescriptor = { mode: write ? 'readwrite' : 'read' }
  if (await handle.queryPermission(descriptor) === 'granted') return true
  return await handle.requestPermission(descriptor) === 'granted'
}

export async function scanProjects(root: FileSystemDirectoryHandle): Promise<DiscoveredProject[]> {
  const found: DiscoveredProject[] = []
  for await (const handle of root.values()) {
    if (handle.kind !== 'directory' || !UUID_PATTERN.test(handle.name)) continue
    let gprjFileName = ''
    for await (const child of handle.values()) {
      if (child.kind === 'file' && child.name.toLowerCase().endsWith('.gprj')) { gprjFileName = child.name; break }
    }
    if (gprjFileName) found.push({ sourceUuid: handle.name, projectName: gprjFileName.replace(/\.gprj$/i, ''), gprjFileName, directory: handle })
  }
  return found.sort((a, b) => a.projectName.localeCompare(b.projectName, 'ja'))
}

async function writeFile(root: FileSystemDirectoryHandle, path: string[], bytes: Uint8Array): Promise<void> {
  const fileName = path.at(-1)
  if (!fileName) return
  let directory = root
  for (const part of path.slice(0, -1)) directory = await directory.getDirectoryHandle(part, { create: true })
  const writable = await (await directory.getFileHandle(fileName, { create: true })).createWritable()
  const copy = new Uint8Array(bytes.byteLength)
  copy.set(bytes)
  await writable.write(copy.buffer)
  await writable.close()
}

export async function restoreArchiveToDirectory(dataRoot: FileSystemDirectoryHandle, archive: Blob, expectedUuid: string): Promise<'created' | 'overwritten' | 'cancelled'> {
  const validated = validateCanonicalArchive(new Uint8Array(await archive.arrayBuffer()), expectedUuid)
  let exists = false
  try { await dataRoot.getDirectoryHandle(validated.rootUuid); exists = true } catch { /* absent */ }
  if (exists && !window.confirm(`UUID ${validated.rootUuid} のフォルダーは既に存在します。上書きしますか？`)) return 'cancelled'
  if (exists) await dataRoot.removeEntry(validated.rootUuid, { recursive: true })
  const target = await dataRoot.getDirectoryHandle(validated.rootUuid, { create: true })
  for (const file of validated.files) await writeFile(target, file.relativePath, file.bytes)
  return exists ? 'overwritten' : 'created'
}

export function triggerDownload(blob: Blob, fileName: string): void {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url; anchor.download = fileName; anchor.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

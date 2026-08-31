import { unzipSync, zipSync } from 'fflate'

export const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/

async function collectFiles(directory: FileSystemDirectoryHandle, prefix: string, result: Record<string, Uint8Array>): Promise<void> {
  for await (const [name, handle] of directory.entries()) {
    const path = prefix ? `${prefix}/${name}` : name
    if (handle.kind === 'directory') await collectFiles(handle, path, result)
    else result[path] = new Uint8Array(await (await handle.getFile()).arrayBuffer())
  }
}

export async function createCanonicalArchive(sourceUuid: string, directory: FileSystemDirectoryHandle): Promise<Blob> {
  if (!UUID_PATTERN.test(sourceUuid)) throw new Error('保存元フォルダー名がUUIDではありません。')
  const files: Record<string, Uint8Array> = {}
  await collectFiles(directory, '', files)
  const gprjFiles = Object.keys(files).filter((path) => !path.includes('/') && path.toLowerCase().endsWith('.gprj'))
  if (gprjFiles.length !== 1) throw new Error('UUIDフォルダー直下にプロジェクト本体（*.gprj）が1つ必要です。')
  return new Blob([zipSync(files, { level: 6 })], { type: 'application/zip' })
}

export interface ValidatedArchive {
  rootUuid: string
  layout: 'flat' | 'wrapped'
  files: Array<{ relativePath: string[]; bytes: Uint8Array }>
}

export interface CanonicalFileSelection {
  archive: Blob
  sourceUuid: string
  projectName: string
  fileName: string
}

function parseRelativeFilePath(path: string): string[] {
  if (!path || path.startsWith('/') || path.includes('\\')) throw new Error('選択ファイルの相対パスを取得できません。')
  const parts = path.split('/')
  if (parts.length < 2 || parts.some((part) => !part || part === '.' || part === '..')) {
    throw new Error('選択ディレクトリに安全でない相対パスが含まれています。')
  }
  return parts
}

export async function createCanonicalArchiveFromFiles(selectedFiles: Iterable<File>): Promise<CanonicalFileSelection> {
  const files = [...selectedFiles]
  if (!files.length) throw new Error('ディレクトリにファイルがありません。')

  const parsed = files.map((file) => ({ file, parts: parseRelativeFilePath(file.webkitRelativePath) }))
  const roots = new Set(parsed.map(({ parts }) => parts[0]!))
  if (roots.size !== 1) throw new Error('選択対象は単一のUUID最上位フォルダーである必要があります。')
  const sourceUuid = [...roots][0]!
  if (!UUID_PATTERN.test(sourceUuid)) throw new Error('選択した最上位フォルダー名がUUID形式ではありません。')

  const seenPaths = new Set<string>()
  for (const { parts } of parsed) {
    const key = parts.join('/').toLowerCase()
    if (seenPaths.has(key)) throw new Error('選択ディレクトリに重複したパスがあります。')
    seenPaths.add(key)
  }
  const gprjFiles = parsed.filter(({ parts }) => parts.length === 2 && parts[1]?.toLowerCase().endsWith('.gprj'))
  if (gprjFiles.length !== 1) throw new Error('UUIDフォルダー直下にプロジェクト本体（*.gprj）が1つ必要です。')

  const archiveFiles: Record<string, Uint8Array> = {}
  for (const { file, parts } of parsed) archiveFiles[parts.slice(1).join('/')] = new Uint8Array(await file.arrayBuffer())
  const projectName = gprjFiles[0]!.parts[1]!.replace(/\.gprj$/i, '')
  return {
    archive: new Blob([zipSync(archiveFiles, { level: 6 })], { type: 'application/zip' }),
    sourceUuid,
    projectName,
    fileName: `${sourceUuid}.zip`,
  }
}

export function validateCanonicalArchive(bytes: Uint8Array, expectedUuid?: string): ValidatedArchive {
  const unzipped = unzipSync(bytes)
  const entries: Array<{ parts: string[]; bytes: Uint8Array; directory: boolean }> = []
  for (const [rawPath, content] of Object.entries(unzipped)) {
    const parts = rawPath.replace(/\\/g, '/').split('/').filter(Boolean)
    if (!parts.length || parts.some((part) => part === '.' || part === '..')) throw new Error('ZIPに安全でないパスが含まれています。')
    entries.push({ parts, bytes: content, directory: rawPath.endsWith('/') })
  }
  const roots = new Set(entries.map(({ parts }) => parts[0]!))
  const possibleWrapper = roots.size === 1 ? [...roots][0]! : null
  const layout: ValidatedArchive['layout'] = possibleWrapper && UUID_PATTERN.test(possibleWrapper) ? 'wrapped' : 'flat'
  if (expectedUuid && !UUID_PATTERN.test(expectedUuid)) throw new Error('指定されたプロジェクトUUIDがcanonical形式ではありません。')
  if (layout === 'flat' && !expectedUuid) throw new Error('UUIDラッパーなしZIPは、ファイル名を「UUID.zip」にしてください。')
  const rootUuid = layout === 'wrapped' ? possibleWrapper! : expectedUuid!
  if (expectedUuid && rootUuid !== expectedUuid) throw new Error('ZIPのUUIDがプロジェクト情報と一致しません。')
  const files: ValidatedArchive['files'] = entries
    .filter(({ directory }) => !directory)
    .map(({ parts, bytes: content }) => ({ relativePath: layout === 'wrapped' ? parts.slice(1) : parts, bytes: content }))
  const gprjFiles = files.filter(({ relativePath }) => relativePath.length === 1 && relativePath[0]?.toLowerCase().endsWith('.gprj'))
  if (gprjFiles.length !== 1) throw new Error('UUIDフォルダー直下にプロジェクト本体（*.gprj）が1つ必要です。')
  return { rootUuid, layout, files }
}

export function uuidFromArchiveFileName(fileName: string): string | null {
  const match = /^([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})(?:-v[0-9]+)?\.zip$/.exec(fileName)
  return match?.[1] ?? null
}

export function validateUploadedArchive(bytes: Uint8Array, fileName: string): ValidatedArchive {
  try {
    // A legacy wrapped archive is authoritative and does not depend on its filename.
    return validateCanonicalArchive(bytes)
  } catch (wrappedOrFlatError) {
    const uuidHint = uuidFromArchiveFileName(fileName)
    if (!uuidHint) throw wrappedOrFlatError
    return validateCanonicalArchive(bytes, uuidHint)
  }
}

import { unzipSync, zipSync } from 'fflate'

export const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/

async function collectFiles(directory: FileSystemDirectoryHandle, prefix: string, result: Record<string, Uint8Array>): Promise<void> {
  for await (const [name, handle] of directory.entries()) {
    const path = `${prefix}/${name}`
    if (handle.kind === 'directory') await collectFiles(handle, path, result)
    else result[path] = new Uint8Array(await (await handle.getFile()).arrayBuffer())
  }
}

export async function createCanonicalArchive(sourceUuid: string, directory: FileSystemDirectoryHandle): Promise<Blob> {
  if (!UUID_PATTERN.test(sourceUuid)) throw new Error('保存元フォルダー名がUUIDではありません。')
  const files: Record<string, Uint8Array> = {}
  await collectFiles(directory, sourceUuid, files)
  const gprjFiles = Object.keys(files).filter((path) => path.split('/').length === 2 && path.toLowerCase().endsWith('.gprj'))
  if (gprjFiles.length !== 1) throw new Error('UUIDフォルダー直下にプロジェクト本体（*.gprj）が1つ必要です。')
  return new Blob([zipSync(files, { level: 6 })], { type: 'application/zip' })
}

export interface ValidatedArchive {
  rootUuid: string
  files: Array<{ relativePath: string[]; bytes: Uint8Array }>
}

export function validateCanonicalArchive(bytes: Uint8Array, expectedUuid?: string): ValidatedArchive {
  const unzipped = unzipSync(bytes)
  const files: ValidatedArchive['files'] = []
  const roots = new Set<string>()
  for (const [rawPath, content] of Object.entries(unzipped)) {
    const parts = rawPath.replace(/\\/g, '/').split('/').filter(Boolean)
    if (!parts.length || parts.some((part) => part === '.' || part === '..')) throw new Error('ZIPに安全でないパスが含まれています。')
    roots.add(parts[0]!)
    if (!rawPath.endsWith('/')) files.push({ relativePath: parts.slice(1), bytes: content })
  }
  if (roots.size !== 1) throw new Error('ZIPの最上位は単一のUUIDフォルダーである必要があります。')
  const rootUuid = [...roots][0]!
  if (!UUID_PATTERN.test(rootUuid)) throw new Error('ZIPの最上位フォルダーがUUIDではありません。')
  if (expectedUuid && rootUuid.toLowerCase() !== expectedUuid.toLowerCase()) throw new Error('ZIPのUUIDがプロジェクト情報と一致しません。')
  const gprjFiles = files.filter(({ relativePath }) => relativePath.length === 1 && relativePath[0]?.toLowerCase().endsWith('.gprj'))
  if (gprjFiles.length !== 1) throw new Error('UUIDフォルダー直下にプロジェクト本体（*.gprj）が1つ必要です。')
  return { rootUuid, files }
}

import { zipSync } from 'fflate'
import { describe, expect, it } from 'vitest'
import { createCanonicalArchiveFromFiles, validateCanonicalArchive } from './archive'

const uuid = 'de795586-5cdb-4ca9-a472-938a1fbfb341'

describe('validateCanonicalArchive', () => {
  it('accepts a single UUID root containing a gprj', () => {
    const zip = zipSync({ [`${uuid}/sample.gprj`]: new Uint8Array([1, 2]) })
    expect(validateCanonicalArchive(zip, uuid).rootUuid).toBe(uuid)
  })

  it('rejects multiple roots', () => {
    const zip = zipSync({ [`${uuid}/sample.gprj`]: new Uint8Array(), 'other/file.txt': new Uint8Array() })
    expect(() => validateCanonicalArchive(zip)).toThrow('単一のUUID')
  })

  it('rejects an archive without a gprj', () => {
    const zip = zipSync({ [`${uuid}/readme.txt`]: new Uint8Array() })
    expect(() => validateCanonicalArchive(zip)).toThrow('*.gprj')
  })

  it('rejects multiple direct gprj files', () => {
    const zip = zipSync({ [`${uuid}/one.gprj`]: new Uint8Array([1]), [`${uuid}/two.gprj`]: new Uint8Array([2]) })
    expect(() => validateCanonicalArchive(zip)).toThrow('1つ')
  })
})

function directoryFile(path: string, content: string): File {
  const file = new File([content], path.split('/').at(-1)!, { type: 'application/octet-stream' })
  Object.defineProperty(file, 'webkitRelativePath', { value: path })
  Object.defineProperty(file, 'arrayBuffer', { value: async () => new TextEncoder().encode(content).buffer })
  return file
}

function blobBytes(blob: Blob): Promise<Uint8Array> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => reader.result instanceof ArrayBuffer ? resolve(new Uint8Array(reader.result)) : reject(new Error('Unexpected FileReader result'))
    reader.onerror = () => reject(reader.error)
    reader.readAsArrayBuffer(blob)
  })
}

describe('createCanonicalArchiveFromFiles', () => {
  it('builds a canonical ZIP from webkitRelativePath files', async () => {
    const selected = await createCanonicalArchiveFromFiles([
      directoryFile(`${uuid}/Factory.gprj`, 'project'),
      directoryFile(`${uuid}/measurements/data.bin`, 'measurement'),
    ])
    expect(selected).toMatchObject({ sourceUuid: uuid, projectName: 'Factory', fileName: `${uuid}.zip` })
    const validated = validateCanonicalArchive(await blobBytes(selected.archive), uuid)
    expect(validated.files.map((file) => file.relativePath.join('/'))).toEqual(expect.arrayContaining(['Factory.gprj', 'measurements/data.bin']))
  })

  it('rejects files from more than one top-level folder', async () => {
    await expect(createCanonicalArchiveFromFiles([
      directoryFile(`${uuid}/Factory.gprj`, 'project'),
      directoryFile('11111111-1111-1111-1111-111111111111/Other.gprj', 'other'),
    ])).rejects.toThrow('単一のUUID')
  })

  it('rejects a non-UUID selected folder', async () => {
    await expect(createCanonicalArchiveFromFiles([
      directoryFile('Factory/Factory.gprj', 'project'),
    ])).rejects.toThrow('UUID形式')
  })

  it('requires exactly one gprj directly under the selected UUID folder', async () => {
    await expect(createCanonicalArchiveFromFiles([
      directoryFile(`${uuid}/nested/Factory.gprj`, 'project'),
      directoryFile(`${uuid}/readme.txt`, 'readme'),
    ])).rejects.toThrow('1つ')
  })
})

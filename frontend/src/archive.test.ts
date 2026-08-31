import { unzipSync, zipSync } from 'fflate'
import { describe, expect, it } from 'vitest'
import { createCanonicalArchiveFromFiles, uuidFromArchiveFileName, validateCanonicalArchive, validateUploadedArchive } from './archive'

const uuid = 'de795586-5cdb-4ca9-a472-938a1fbfb341'

describe('validateCanonicalArchive', () => {
  it('accepts a legacy UUID-wrapped archive and normalizes its paths', () => {
    const zip = zipSync({ [`${uuid}/sample.gprj`]: new Uint8Array([1, 2]) })
    expect(validateCanonicalArchive(zip)).toMatchObject({ rootUuid: uuid, layout: 'wrapped', files: [{ relativePath: ['sample.gprj'] }] })
  })

  it('accepts a flat archive when its UUID is supplied', () => {
    const zip = zipSync({ 'sample.gprj': new Uint8Array([1]), 'measurements/data.bin': new Uint8Array([2]) })
    expect(validateCanonicalArchive(zip, uuid)).toMatchObject({ rootUuid: uuid, layout: 'flat' })
  })

  it('requires a UUID hint for a flat archive', () => {
    const zip = zipSync({ 'sample.gprj': new Uint8Array([1]) })
    expect(() => validateCanonicalArchive(zip)).toThrow('UUID.zip')
  })

  it.each([`${uuid}.zip`, `${uuid}-v12.zip`])('accepts a flat upload named %s', (fileName) => {
    const zip = zipSync({ 'sample.gprj': new Uint8Array([1]) })
    expect(validateUploadedArchive(zip, fileName)).toMatchObject({ rootUuid: uuid, layout: 'flat' })
    expect(uuidFromArchiveFileName(fileName)).toBe(uuid)
  })

  it('accepts a legacy wrapped upload regardless of its filename', () => {
    const zip = zipSync({ [`${uuid}/sample.gprj`]: new Uint8Array([1]) })
    expect(validateUploadedArchive(zip, 'legacy-backup.zip')).toMatchObject({ rootUuid: uuid, layout: 'wrapped' })
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
    const bytes = await blobBytes(selected.archive)
    expect(Object.keys(unzipSync(bytes))).toEqual(expect.arrayContaining(['Factory.gprj', 'measurements/data.bin']))
    expect(Object.keys(unzipSync(bytes)).some((path) => path.startsWith(`${uuid}/`))).toBe(false)
    const validated = validateCanonicalArchive(bytes, uuid)
    expect(validated.layout).toBe('flat')
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

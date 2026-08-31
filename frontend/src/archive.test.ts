import { zipSync } from 'fflate'
import { describe, expect, it } from 'vitest'
import { validateCanonicalArchive } from './archive'

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

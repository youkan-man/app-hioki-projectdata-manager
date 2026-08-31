import { afterEach, describe, expect, it, vi } from 'vitest'
import { getProjectConfiguration, getProjects, saveProjectConfiguration, updateProject } from './api'
import type { ProjectId } from './types'

afterEach(() => vi.unstubAllGlobals())

describe('API contract', () => {
  it('maps the backend ProjectRead shape at the network boundary', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      items: [{
        id: '11111111-1111-1111-1111-111111111111',
        source_uuid: 'de795586-5cdb-4ca9-a472-938a1fbfb341',
        project_name: 'Factory Inspection', display_name: 'Line A inspection', description: 'production line',
        created_at: '2026-08-01T00:00:00Z', updated_at: '2026-08-02T00:00:00Z', deleted_at: null,
        versions: [{ id: '22222222-2222-2222-2222-222222222222', version_number: 2, size_bytes: 2048, note: 'updated', created_at: '2026-08-02T00:00:00Z' }],
      }], total: 1,
    }), { status: 200, headers: { 'Content-Type': 'application/json' } })))

    const [project] = await getProjects(false)
    expect(project).toMatchObject({ projectName: 'Factory Inspection', displayName: 'Line A inspection', note: 'production line' })
    expect(project?.versions[0]).toMatchObject({ version: 2, archiveSize: 2048 })
  })

  it('uses name and description for PATCH', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    await updateProject('11111111-1111-1111-1111-111111111111' as ProjectId, { displayName: 'New name', note: 'New description' })
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({ name: 'New name', description: 'New description' })
  })

  it('maps both project and layout configuration documents', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      version: 3,
      project: { filename: 'Factory.gprj', config: { channels: [1, 2] } },
      layout: { filename: 'layout.lay', config: { panels: [{ id: 'main' }] } },
    }), { status: 200, headers: { 'Content-Type': 'application/json' } })))
    await expect(getProjectConfiguration('11111111-1111-1111-1111-111111111111' as ProjectId)).resolves.toEqual({
      filename: 'Factory.gprj', version: 3, config: { channels: [1, 2] },
      layoutFilename: 'layout.lay', layout: { panels: [{ id: 'main' }] },
    })
  })

  it('represents a missing layout explicitly', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      version: 1, project: { filename: 'Factory.gprj', config: {} }, layout: null,
    }), { status: 200, headers: { 'Content-Type': 'application/json' } })))
    await expect(getProjectConfiguration('11111111-1111-1111-1111-111111111111' as ProjectId)).resolves.toMatchObject({ layout: null, layoutFilename: null })
  })

  it('saves project and layout JSON together', async () => {
    const project = {
      id: '11111111-1111-1111-1111-111111111111', source_uuid: 'de795586-5cdb-4ca9-a472-938a1fbfb341',
      project_name: 'Factory', display_name: 'Factory', description: null,
      created_at: '2026-08-01T00:00:00Z', updated_at: '2026-08-02T00:00:00Z', deleted_at: null, versions: [],
    }
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(project), { status: 201, headers: { 'Content-Type': 'application/json' } }))
    vi.stubGlobal('fetch', fetchMock)
    await saveProjectConfiguration(project.id as ProjectId, { config: { channel: 1 }, layout: { panel: 'main' }, note: 'both changed' })
    expect(JSON.parse(fetchMock.mock.calls[0]?.[1]?.body as string)).toEqual({ project: { channel: 1 }, layout: { panel: 'main' }, note: 'both changed' })
  })
})

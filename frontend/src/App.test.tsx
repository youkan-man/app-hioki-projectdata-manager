import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('project and version notes', () => {
  it('prioritizes the project column and downloads the latest ZIP without expanding history', async () => {
    const activeUuid = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
    const deletedUuid = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'
    const projects = { items: [
      { id: '11111111-1111-1111-1111-111111111111', source_uuid: activeUuid, name: 'Active project', description: null, created_at: '2026-08-01T00:00:00Z', updated_at: '2026-08-02T00:00:00Z', deleted_at: null, versions: [{ id: '22222222-2222-2222-2222-222222222222', version_number: 3, size_bytes: 1200, note: 'active latest', created_at: '2026-08-02T00:00:00Z' }] },
      { id: '33333333-3333-3333-3333-333333333333', source_uuid: deletedUuid, name: 'Deleted project', description: null, created_at: '2026-08-01T00:00:00Z', updated_at: '2026-08-03T00:00:00Z', deleted_at: '2026-08-04T00:00:00Z', versions: [{ id: '44444444-4444-4444-4444-444444444444', version_number: 5, size_bytes: 2400, note: 'deleted latest', created_at: '2026-08-03T00:00:00Z' }] },
      { id: '55555555-5555-5555-5555-555555555555', source_uuid: 'cccccccc-cccc-cccc-cccc-cccccccccccc', name: 'Empty project', description: null, created_at: '2026-08-01T00:00:00Z', updated_at: '2026-08-01T00:00:00Z', deleted_at: null, versions: [] },
    ], total: 3 }
    const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = String(input)
      return Promise.resolve(url.endsWith('/archive') ? new Response(new Blob(['zip']), { status: 200 }) : new Response(JSON.stringify(projects), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    })
    vi.stubGlobal('fetch', fetchMock)
    class TestURL extends URL {
      static createObjectURL = vi.fn(() => 'blob:test-archive')
      static revokeObjectURL = vi.fn()
    }
    vi.stubGlobal('URL', TestURL)
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)

    render(<App />)
    expect(await screen.findByText('Active project')).not.toBeNull()
    expect(screen.queryByRole('columnheader', { name: 'UUID' })).toBeNull()
    expect(screen.queryByText(activeUuid)).toBeNull()
    expect(screen.queryByText(deletedUuid)).toBeNull()
    expect(screen.getByRole('columnheader', { name: 'プロジェクト' }).classList.contains('project-column')).toBe(true)
    expect(screen.queryByText('active latest')).toBeNull()

    const latestButtons = screen.getAllByRole('button', { name: /最新バージョンZIPをダウンロード/ })
    expect(latestButtons).toHaveLength(3)
    expect(screen.getByRole('button', { name: 'Empty project の最新バージョンZIPをダウンロード' }).hasAttribute('disabled')).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Active project の最新バージョンZIPをダウンロード' }))
    await vi.waitFor(() => expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/versions/22222222-2222-2222-2222-222222222222/archive'))).toBe(true))
    fireEvent.click(screen.getByRole('button', { name: 'Deleted project の最新バージョンZIPをダウンロード' }))
    await vi.waitFor(() => expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/versions/44444444-4444-4444-4444-444444444444/archive'))).toBe(true))
    await new Promise((resolve) => setTimeout(resolve, 1050))
  })

  it('renders notes on dedicated second rows', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      items: [{
        id: '11111111-1111-1111-1111-111111111111',
        source_uuid: 'de795586-5cdb-4ca9-a472-938a1fbfb341',
        name: 'Factory Inspection',
        description: 'Project planning note',
        created_at: '2026-08-01T00:00:00Z',
        updated_at: '2026-08-02T00:00:00Z',
        deleted_at: null,
        versions: [{
          id: '22222222-2222-2222-2222-222222222222',
          version_number: 1,
          size_bytes: 1024,
          note: 'Version measurement note',
          created_at: '2026-08-02T00:00:00Z',
        }],
      }],
      total: 1,
    }), { status: 200, headers: { 'Content-Type': 'application/json' } })))

    render(<App />)
    const projectNote = await screen.findByText('Project planning note')
    expect(projectNote.closest('.project-memo')).not.toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'バージョン履歴を展開' }))
    const versionNote = await screen.findByText('Version measurement note')
    expect(versionNote.closest('.version-memo')).not.toBeNull()
    expect(screen.getAllByText('メモ')).toHaveLength(2)
  })

  it('opens the same two-tab configuration modal from context menu and gear', async () => {
    const projectResponse = {
      items: [{
        id: '11111111-1111-1111-1111-111111111111', source_uuid: 'de795586-5cdb-4ca9-a472-938a1fbfb341',
        name: 'Factory Inspection', description: 'Right click target', created_at: '2026-08-01T00:00:00Z',
        updated_at: '2026-08-02T00:00:00Z', deleted_at: null, versions: [],
      }], total: 1,
    }
    const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = String(input)
      const body = url.endsWith('/configuration')
        ? { version: 4, project: { filename: 'Factory.gprj', config: { sampleRate: 1000 } }, layout: { filename: 'layout.lay', config: { panel: 'main' } } }
        : projectResponse
      return Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)

    const row = (await screen.findByText('Right click target')).closest('tr')
    expect(row).not.toBeNull()
    fireEvent.contextMenu(row!, { clientX: 5000, clientY: 5000 })
    const menu = screen.getByRole('menu')
    expect(Number.parseInt(menu.style.left)).toBeLessThan(window.innerWidth)
    expect(Number.parseInt(menu.style.top)).toBeLessThan(window.innerHeight)
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('menu')).toBeNull()

    fireEvent.contextMenu(row!, { clientX: 40, clientY: 50 })
    fireEvent.pointerDown(document.body)
    expect(screen.queryByRole('menu')).toBeNull()
    fireEvent.contextMenu(row!, { clientX: 40, clientY: 50 })
    fireEvent.click(screen.getByRole('menuitem', { name: /プロジェクト設定/ }))
    expect(await screen.findByRole('dialog', { name: 'プロジェクト設定' })).not.toBeNull()
    expect(screen.getByRole('tab', { name: /プロジェクト設定/ }).getAttribute('aria-selected')).toBe('true')
    fireEvent.click(screen.getByRole('tab', { name: /レイアウト/ }))
    expect((screen.getByLabelText('レイアウト JSON') as HTMLTextAreaElement).value).toContain('"panel": "main"')
    fireEvent.click(screen.getAllByRole('button', { name: '閉じる' }).at(-1)!)

    fireEvent.click(screen.getByRole('button', { name: 'Factory Inspection のプロジェクト設定' }))
    expect(await screen.findByRole('dialog', { name: 'プロジェクト設定' })).not.toBeNull()
  })

  it('keeps deleted project configuration read-only and shows a missing layout', async () => {
    const fetchMock = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = String(input)
      const body = url.endsWith('/configuration')
        ? { version: 2, project: { filename: 'Deleted.gprj', config: { locked: true } }, layout: null }
        : { items: [{
          id: '33333333-3333-3333-3333-333333333333', source_uuid: '44444444-4444-4444-4444-444444444444',
          name: 'Deleted project', description: null, created_at: '2026-08-01T00:00:00Z',
          updated_at: '2026-08-02T00:00:00Z', deleted_at: '2026-08-03T00:00:00Z', versions: [],
        }], total: 1 }
      return Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)
    fireEvent.click(await screen.findByRole('button', { name: 'Deleted project のプロジェクト設定' }))
    expect(await screen.findByText('削除済みプロジェクトの設定は閲覧と出力のみ可能です。')).not.toBeNull()
    expect((screen.getByLabelText('プロジェクト設定 JSON') as HTMLTextAreaElement).readOnly).toBe(true)
    expect(screen.queryByRole('button', { name: '編集' })).toBeNull()
    fireEvent.click(screen.getByRole('tab', { name: /レイアウト/ }))
    expect(screen.getByText('layout.lay はありません')).not.toBeNull()
    expect(screen.getByRole('button', { name: 'このファイルを出力' }).hasAttribute('disabled')).toBe(true)
    expect(screen.queryByRole('button', { name: 'レイアウトJSONを作成' })).toBeNull()
  })
})

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App'

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('project and version notes', () => {
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
})

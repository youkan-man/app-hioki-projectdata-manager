import { fireEvent, render, screen, cleanup } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { ContextMenu } from './ContextMenu'

afterEach(() => { cleanup(); document.body.innerHTML = '' })

it('focuses enabled actions, skips disabled entries, navigates, and closes on Escape', () => {
  const trigger = document.createElement('button'); document.body.append(trigger); trigger.focus()
  const close = vi.fn(), run = vi.fn()
  const { unmount } = render(<ContextMenu position={{ x: 10, y: 10, trigger }} onClose={close} actions={[{ label: '閲覧', run }, { label: 'CSV', run, disabled: true }, { label: '削除', run }]} />)
  expect(document.activeElement).toBe(screen.getByRole('menuitem', { name: '閲覧' }))
  fireEvent.keyDown(screen.getByRole('menu'), { key: 'ArrowDown' })
  expect(document.activeElement).toBe(screen.getByRole('menuitem', { name: '削除' }))
  fireEvent.keyDown(screen.getByRole('menu'), { key: 'Home' })
  expect(document.activeElement).toBe(screen.getByRole('menuitem', { name: '閲覧' }))
  fireEvent.keyDown(screen.getByRole('menu'), { key: 'Escape' })
  expect(close).toHaveBeenCalledOnce()
  unmount(); expect(document.activeElement).toBe(trigger)
})

it('offers the same click actions and closes on outside pointer input', () => {
  const trigger = document.createElement('button'); document.body.append(trigger)
  const close = vi.fn(), run = vi.fn()
  render(<ContextMenu position={{ x: 9999, y: 9999, trigger }} onClose={close} actions={[{ label: '閲覧', run }]} />)
  fireEvent.click(screen.getByRole('menuitem'))
  expect(run).toHaveBeenCalledOnce(); expect(close).toHaveBeenCalledOnce()
  fireEvent.pointerDown(trigger); expect(close).toHaveBeenCalledTimes(2)
})

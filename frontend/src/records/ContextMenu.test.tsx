import { fireEvent, render, screen, cleanup } from '@testing-library/react'
import { afterEach, expect, it, vi } from 'vitest'
import { ContextMenu } from './ContextMenu'

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); document.body.innerHTML = '' })

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

it('renders outside the workspace and clamps every edge on a narrow viewport', () => {
  vi.stubGlobal('innerWidth', 390); vi.stubGlobal('innerHeight', 300)
  vi.stubGlobal('visualViewport', undefined)
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({ width: 280, height: 180 } as DOMRect)
  const trigger = document.createElement('button'); document.body.append(trigger)
  const { container } = render(<ContextMenu position={{ x: 1500, y: 900, trigger }} onClose={vi.fn()} actions={[{ label: '閲覧', run: vi.fn() }]} />)
  const menu = screen.getByRole('menu')
  expect(menu.parentElement).toBe(document.body)
  expect(container.contains(menu)).toBe(false)
  expect(menu.style.left).toBe('102px'); expect(menu.style.top).toBe('112px')
})

it('uses visual viewport offsets when the viewport is zoomed', () => {
  const viewport = Object.assign(new EventTarget(), { width: 240, height: 300, offsetLeft: 20, offsetTop: 30 })
  vi.stubGlobal('visualViewport', viewport)
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({ width: 180, height: 120 } as DOMRect)
  const trigger = document.createElement('button'); document.body.append(trigger)
  const close = vi.fn()
  const { unmount } = render(<ContextMenu position={{ x: 999, y: 999, trigger }} onClose={close} actions={[{ label: '閲覧', run: vi.fn() }]} />)
  expect(screen.getByRole('menu').style.left).toBe('72px')
  expect(screen.getByRole('menu').style.top).toBe('202px')
  viewport.dispatchEvent(new Event('resize')); expect(close).toHaveBeenCalledOnce()
  unmount(); viewport.dispatchEvent(new Event('resize')); expect(close).toHaveBeenCalledOnce()
})

it('does not scroll the document when focusing an action or restoring its trigger', () => {
  const trigger = document.createElement('button'); document.body.append(trigger)
  const focus = vi.spyOn(HTMLElement.prototype, 'focus')
  const { unmount } = render(<ContextMenu position={{ x: 1000, y: 1000, trigger }} onClose={vi.fn()} actions={[{ label: '閲覧', run: vi.fn() }, { label: '編集', run: vi.fn() }]} />)
  expect(focus).toHaveBeenLastCalledWith({ preventScroll: true })
  fireEvent.keyDown(screen.getByRole('menu'), { key: 'End' })
  expect(document.activeElement).toBe(screen.getByRole('menuitem', { name: '編集' }))
  expect(focus).toHaveBeenLastCalledWith({ preventScroll: true })
  unmount()
  expect(document.activeElement).toBe(trigger)
  expect(focus).toHaveBeenLastCalledWith({ preventScroll: true })
})

it('allows internal menu scrolling but dismisses on external scrolling', () => {
  const trigger = document.createElement('button'); document.body.append(trigger)
  const close = vi.fn()
  const { unmount } = render(<ContextMenu position={{ x: 0, y: 0, trigger }} onClose={close} actions={[{ label: '閲覧', run: vi.fn() }]} />)
  fireEvent.scroll(screen.getByRole('menu'))
  expect(close).not.toHaveBeenCalled()
  fireEvent.scroll(window); expect(close).toHaveBeenCalledOnce()
  unmount(); fireEvent.scroll(window); expect(close).toHaveBeenCalledOnce()
})

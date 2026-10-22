import { useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'

export type MenuAction = { label: string; run: () => void; disabled?: boolean; danger?: boolean }
export type MenuPosition = { x: number; y: number; trigger: HTMLElement }

export function ContextMenu({ position, actions, onClose }: { position: MenuPosition; actions: MenuAction[]; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null)
  const [point, setPoint] = useState({ x: position.x, y: position.y })
  useLayoutEffect(() => {
    const element = ref.current!
    const rectangle = element.getBoundingClientRect()
    const viewport = window.visualViewport
    const left = viewport?.offsetLeft ?? 0, top = viewport?.offsetTop ?? 0
    const width = viewport?.width ?? window.innerWidth, height = viewport?.height ?? window.innerHeight
    setPoint({
      x: Math.max(left + 8, Math.min(position.x, left + width - rectangle.width - 8)),
      y: Math.max(top + 8, Math.min(position.y, top + height - rectangle.height - 8)),
    })
    // Focusing an off-screen table action must not move the document or its scroll container.
    element.querySelector<HTMLButtonElement>('button:not(:disabled)')?.focus({ preventScroll: true })
    function outside(event: PointerEvent) { if (!element.contains(event.target as Node)) onClose() }
    function close() { onClose() }
    function scroll(event: Event) {
      // Long menus may scroll internally; only an external scroll invalidates their anchor.
      if (event.target instanceof Node && element.contains(event.target)) return
      onClose()
    }
    document.addEventListener('pointerdown', outside)
    window.addEventListener('resize', close)
    window.addEventListener('scroll', scroll, true)
    viewport?.addEventListener('resize', close)
    viewport?.addEventListener('scroll', close)
    return () => {
      document.removeEventListener('pointerdown', outside)
      window.removeEventListener('resize', close)
      window.removeEventListener('scroll', scroll, true)
      viewport?.removeEventListener('resize', close)
      viewport?.removeEventListener('scroll', close)
      if (position.trigger.isConnected) position.trigger.focus({ preventScroll: true })
    }
  }, [position, onClose])
  // The body portal avoids clipping and transformed containing blocks in either workspace.
  return createPortal(<div ref={ref} className="record-context-menu" role="menu" aria-label="記録の操作" style={{ left: point.x, top: point.y }} onKeyDown={(event) => {
    const buttons = Array.from(ref.current!.querySelectorAll<HTMLButtonElement>('button:not(:disabled)'))
    const current = buttons.indexOf(document.activeElement as HTMLButtonElement)
    let next = current
    if (event.key === 'ArrowDown') next = (current + 1) % buttons.length
    else if (event.key === 'ArrowUp') next = (current - 1 + buttons.length) % buttons.length
    else if (event.key === 'Home') next = 0
    else if (event.key === 'End') next = buttons.length - 1
    else if (event.key === 'Escape' || event.key === 'Tab') { event.preventDefault(); onClose(); return }
    else return
    event.preventDefault(); buttons[next]?.focus({ preventScroll: true })
  }}>{actions.map((action) => <button key={action.label} role="menuitem" className={action.danger ? 'danger-text' : ''} disabled={action.disabled} onClick={() => { onClose(); action.run() }}>{action.label}</button>)}</div>, document.body)
}

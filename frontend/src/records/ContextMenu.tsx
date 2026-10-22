import { useLayoutEffect, useRef, useState } from 'react'

export type MenuAction = { label: string; run: () => void; disabled?: boolean; danger?: boolean }
export type MenuPosition = { x: number; y: number; trigger: HTMLElement }

export function ContextMenu({ position, actions, onClose }: { position: MenuPosition; actions: MenuAction[]; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null)
  const [point, setPoint] = useState({ x: position.x, y: position.y })
  useLayoutEffect(() => {
    const element = ref.current!
    const rectangle = element.getBoundingClientRect()
    setPoint({ x: Math.max(8, Math.min(position.x, innerWidth - rectangle.width - 8)), y: Math.max(8, Math.min(position.y, innerHeight - rectangle.height - 8)) })
    element.querySelector<HTMLButtonElement>('button:not(:disabled)')?.focus()
    function outside(event: PointerEvent) { if (!element.contains(event.target as Node)) onClose() }
    function close() { onClose() }
    document.addEventListener('pointerdown', outside)
    window.addEventListener('resize', close)
    window.addEventListener('scroll', close, true)
    return () => {
      document.removeEventListener('pointerdown', outside)
      window.removeEventListener('resize', close)
      window.removeEventListener('scroll', close, true)
      if (position.trigger.isConnected) position.trigger.focus()
    }
  }, [position, onClose])
  return <div ref={ref} className="record-context-menu" role="menu" aria-label="記録の操作" style={{ left: point.x, top: point.y }} onKeyDown={(event) => {
    const buttons = Array.from(ref.current!.querySelectorAll<HTMLButtonElement>('button:not(:disabled)'))
    const current = buttons.indexOf(document.activeElement as HTMLButtonElement)
    let next = current
    if (event.key === 'ArrowDown') next = (current + 1) % buttons.length
    else if (event.key === 'ArrowUp') next = (current - 1 + buttons.length) % buttons.length
    else if (event.key === 'Home') next = 0
    else if (event.key === 'End') next = buttons.length - 1
    else if (event.key === 'Escape' || event.key === 'Tab') { event.preventDefault(); onClose(); return }
    else return
    event.preventDefault(); buttons[next]?.focus()
  }}>{actions.map((action) => <button key={action.label} role="menuitem" className={action.danger ? 'danger-text' : ''} disabled={action.disabled} onClick={() => { onClose(); action.run() }}>{action.label}</button>)}</div>
}

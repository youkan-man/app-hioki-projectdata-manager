import { useEffect, useLayoutEffect, useState } from 'react'
import App from './App'
import Records from './records/Records'

export default function Workspace() {
  const [page, setPage] = useState(location.hash === '#records' ? 'records' : 'projects')
  useEffect(() => {
    const change = () => setPage(location.hash === '#records' ? 'records' : 'projects')
    window.addEventListener('hashchange', change)
    return () => window.removeEventListener('hashchange', change)
  }, [])
  useLayoutEffect(() => {
    const previous = document.body.dataset.workspace
    document.body.dataset.workspace = page
    return () => {
      if (previous === undefined) delete document.body.dataset.workspace
      else document.body.dataset.workspace = previous
    }
  }, [page])
  return <>
    <nav className="workspace-nav" aria-label="データの種類">
      <button aria-current={page === 'projects' ? 'page' : undefined} onClick={() => { location.hash = 'projects'; setPage('projects') }}>プロジェクト</button>
      <button aria-current={page === 'records' ? 'page' : undefined} onClick={() => { location.hash = 'records'; setPage('records') }}>レコードデータ</button>
    </nav>
    <div hidden={page !== 'projects'}><App /></div>
    <div hidden={page !== 'records'}><Records /></div>
  </>
}

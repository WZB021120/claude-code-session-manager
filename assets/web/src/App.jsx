import { useState, useEffect, useCallback, useDeferredValue } from 'react'
import { Search, MessageSquare, Tag, Calendar, Download, Trash2, BarChart3, X, FolderOpen, Clock, Plus, StickyNote, Loader2, Terminal, FileText, Brain, ChevronDown, ChevronRight, ChevronLeft, AlertCircle, Wrench, CheckSquare, Square, ChevronsLeft, ChevronsRight } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

const API_BASE = ''

/* ======== 内容块渲染组件 ======== */

function ThinkingBlock({ text }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="my-2 border border-purple-200 rounded-lg overflow-hidden bg-purple-50/50">
      <button onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-3 py-2 text-xs font-medium text-purple-700 hover:bg-purple-100/50 transition-colors cursor-pointer">
        <Brain className="w-3.5 h-3.5" /> 思考过程
        {open ? <ChevronDown className="w-3.5 h-3.5 ml-auto" /> : <ChevronRight className="w-3.5 h-3.5 ml-auto" />}
      </button>
      {open && (
        <div className="px-3 pb-3 text-xs text-purple-800/80 whitespace-pre-wrap leading-relaxed border-t border-purple-100 pt-2 max-h-80 overflow-y-auto">{text}</div>
      )}
    </div>
  )
}

function ToolUseBlock({ block }) {
  const name = block.tool_name || 'unknown'
  const isBash = name === 'Bash'
  const isFile = name === 'Write' || name === 'Edit' || name === 'Read'
  return (
    <div className="my-2 border border-amber-200 rounded-lg overflow-hidden bg-amber-50/40">
      <div className="flex items-center gap-2 px-3 py-2 text-xs font-medium text-amber-800">
        {isBash ? <Terminal className="w-3.5 h-3.5" /> : isFile ? <FileText className="w-3.5 h-3.5" /> : <Wrench className="w-3.5 h-3.5" />}
        <span className="font-semibold">{name}</span>
        {block.description && <span className="text-amber-600 font-normal">— {block.description}</span>}
      </div>
      {isBash && block.command && (<div className="mx-3 mb-2 bg-slate-800 text-green-400 text-xs font-mono px-3 py-2 rounded-md overflow-x-auto">$ {block.command}</div>)}
      {isFile && block.file_path && (<div className="mx-3 mb-2 text-xs text-amber-700 font-mono bg-amber-100/60 px-3 py-1.5 rounded-md truncate">📄 {block.file_path}</div>)}
      {block.input_summary && (<div className="mx-3 mb-2 text-xs text-amber-700 bg-amber-100/50 px-3 py-1.5 rounded-md overflow-x-auto whitespace-pre-wrap break-all max-h-32 overflow-y-auto">{block.input_summary}</div>)}
    </div>
  )
}

function ToolResultBlock({ block }) {
  const [open, setOpen] = useState(false)
  const isLong = block.text && block.text.length > 300
  const displayText = (!isLong || open) ? block.text : block.text.slice(0, 300) + '...'
  return (
    <div className={`my-2 border rounded-lg overflow-hidden ${block.is_error ? 'border-red-200 bg-red-50/40' : 'border-slate-200 bg-slate-50/60'}`}>
      <div className="flex items-center gap-2 px-3 py-1.5 text-xs font-medium text-slate-500">
        {block.is_error ? <AlertCircle className="w-3.5 h-3.5 text-red-500" /> : <ChevronRight className="w-3.5 h-3.5" />}
        {block.is_error ? '执行出错' : '执行结果'}
      </div>
      <div className={`mx-3 mb-2 text-xs font-mono px-3 py-2 rounded-md overflow-x-auto whitespace-pre-wrap break-all max-h-64 overflow-y-auto ${block.is_error ? 'bg-red-100/60 text-red-800' : 'bg-slate-100 text-slate-700'}`}>{displayText}</div>
      {isLong && (<button onClick={() => setOpen(!open)} className="px-3 pb-2 text-xs text-blue-500 hover:text-blue-700 cursor-pointer">{open ? '收起' : '展开全部'}</button>)}
    </div>
  )
}

function MessageBlocks({ blocks }) {
  return (
    <>{blocks.map((block, i) => {
      if (block.type === 'text') return (
        <div key={i} className="prose prose-sm prose-slate max-w-none break-words prose-headings:text-slate-800 prose-headings:font-heading prose-p:text-slate-700 prose-p:leading-relaxed prose-p:my-1.5 prose-a:text-blue-600 prose-code:text-pink-600 prose-code:bg-slate-100 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-xs prose-code:before:content-none prose-code:after:content-none prose-pre:bg-slate-800 prose-pre:text-slate-100 prose-pre:rounded-lg prose-pre:text-xs prose-li:text-slate-700 prose-li:my-0.5 prose-blockquote:border-blue-300 prose-blockquote:text-slate-600 prose-table:text-sm prose-th:bg-slate-100 prose-th:text-slate-700 prose-td:border-slate-200 prose-strong:text-slate-800 prose-hr:border-slate-200">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{block.text}</ReactMarkdown>
        </div>
      )
      if (block.type === 'thinking') return <ThinkingBlock key={i} text={block.text} />
      if (block.type === 'tool_use') return <ToolUseBlock key={i} block={block} />
      if (block.type === 'tool_result') return <ToolResultBlock key={i} block={block} />
      return null
    })}</>
  )
}

/* ======== 分页组件 ======== */

function Pagination({ page, totalPages, onPageChange }) {
  if (totalPages <= 1) return null

  const getPages = () => {
    const pages = []
    const delta = 2
    const left = Math.max(2, page - delta)
    const right = Math.min(totalPages - 1, page + delta)
    pages.push(1)
    if (left > 2) pages.push('...')
    for (let i = left; i <= right; i++) pages.push(i)
    if (right < totalPages - 1) pages.push('...')
    if (totalPages > 1) pages.push(totalPages)
    return pages
  }

  return (
    <div className="flex items-center justify-center gap-1 mt-6">
      <button onClick={() => onPageChange(1)} disabled={page === 1}
        className="p-1.5 rounded-lg hover:bg-slate-100 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer transition-colors">
        <ChevronsLeft className="w-4 h-4 text-slate-500" />
      </button>
      <button onClick={() => onPageChange(page - 1)} disabled={page === 1}
        className="p-1.5 rounded-lg hover:bg-slate-100 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer transition-colors">
        <ChevronLeft className="w-4 h-4 text-slate-500" />
      </button>
      {getPages().map((p, i) =>
        p === '...' ? (
          <span key={`dot-${i}`} className="px-2 text-slate-400 text-sm">…</span>
        ) : (
          <button key={p} onClick={() => onPageChange(p)}
            className={`w-8 h-8 rounded-lg text-sm font-medium transition-colors cursor-pointer ${p === page ? 'bg-blue-600 text-white shadow-sm' : 'text-slate-600 hover:bg-slate-100'}`}>
            {p}
          </button>
        )
      )}
      <button onClick={() => onPageChange(page + 1)} disabled={page === totalPages}
        className="p-1.5 rounded-lg hover:bg-slate-100 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer transition-colors">
        <ChevronRight className="w-4 h-4 text-slate-500" />
      </button>
      <button onClick={() => onPageChange(totalPages)} disabled={page === totalPages}
        className="p-1.5 rounded-lg hover:bg-slate-100 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer transition-colors">
        <ChevronsRight className="w-4 h-4 text-slate-500" />
      </button>
    </div>
  )
}

/* ======== 主应用 ======== */

function App() {
  const [sessions, setSessions] = useState([])
  const [stats, setStats] = useState(null)
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedSession, setSelectedSession] = useState(null)
  const [selectedTags, setSelectedTags] = useState([])
  const [loading, setLoading] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [showStats, setShowStats] = useState(false)
  const [noteInput, setNoteInput] = useState('')
  const [tagInput, setTagInput] = useState('')
  const [showNoteEditor, setShowNoteEditor] = useState(false)
  const [showTagEditor, setShowTagEditor] = useState(false)
  // 分页
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [total, setTotal] = useState(0)
  // 多选
  const [selectedIds, setSelectedIds] = useState(new Set())
  const [selectMode, setSelectMode] = useState(false)

  const deferredSearchTerm = useDeferredValue(searchTerm)

  useEffect(() => { loadSessions(1); loadStats() }, [])

  const loadSessions = async (p = page) => {
    setLoading(true)
    try {
      const r = await fetch(`${API_BASE}/api/sessions?page=${p}&page_size=20`)
      const d = await r.json()
      if (d.sessions) {
        setSessions(d.sessions)
        setPage(d.page)
        setTotalPages(d.total_pages)
        setTotal(d.total)
      } else if (Array.isArray(d)) {
        setSessions(d)
      } else {
        setSessions([])
      }
    } catch (e) { console.error('加载会话失败:', e); setSessions([]) }
    finally { setLoading(false) }
  }

  const loadStats = async () => {
    try { const r = await fetch(`${API_BASE}/api/stats`); setStats(await r.json()) }
    catch (e) { console.error('加载统计失败:', e) }
  }

  const handleSearch = useCallback(async () => {
    if (!deferredSearchTerm.trim()) { loadSessions(1); return }
    setLoading(true)
    try {
      const r = await fetch(`${API_BASE}/api/search?q=${encodeURIComponent(deferredSearchTerm)}`)
      const d = await r.json()
      setSessions(Array.isArray(d) ? d : [])
      setTotalPages(1)
      setPage(1)
      setTotal(Array.isArray(d) ? d.length : 0)
    } catch (e) { console.error('搜索失败:', e) }
    finally { setLoading(false) }
  }, [deferredSearchTerm])

  useEffect(() => { handleSearch() }, [deferredSearchTerm, handleSearch])

  const handlePageChange = (p) => {
    setSelectedIds(new Set())
    loadSessions(p)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const handleSelectSession = async (session) => {
    if (selectMode) { toggleSelect(session.id); return }
    setDetailLoading(true)
    setSelectedSession({ ...session, messages: [] })
    setShowNoteEditor(false); setShowTagEditor(false)
    try {
      const r = await fetch(`${API_BASE}/api/sessions/${session.id}`)
      if (r.ok) { const d = await r.json(); setSelectedSession(d); setNoteInput(d.note || '') }
      else { setSelectedSession(prev => ({ ...prev, error: '加载失败' })) }
    } catch (e) { setSelectedSession(prev => ({ ...prev, error: '网络错误' })) }
    finally { setDetailLoading(false) }
  }

  const handleDelete = async (id) => {
    if (!confirm('确定要删除这个会话吗？')) return
    try {
      const r = await fetch(`${API_BASE}/api/sessions/${id}`, { method: 'DELETE' })
      if (r.ok) { loadSessions(); loadStats(); if (selectedSession?.id === id) setSelectedSession(null) }
    } catch (e) { console.error('删除失败:', e) }
  }

  const handleBatchDelete = async () => {
    if (selectedIds.size === 0) return
    if (!confirm(`确定要删除选中的 ${selectedIds.size} 个会话吗？`)) return
    try {
      const r = await fetch(`${API_BASE}/api/sessions/batch-delete`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ids: [...selectedIds] })
      })
      if (r.ok) {
        setSelectedIds(new Set())
        setSelectMode(false)
        loadSessions()
        loadStats()
      }
    } catch (e) { console.error('批量删除失败:', e) }
  }

  const handleBatchExport = async (fmt = 'md') => {
    for (const id of selectedIds) {
      await handleExport(id, fmt)
    }
  }

  const handleExport = async (id, fmt = 'md') => {
    try {
      const r = await fetch(`${API_BASE}/api/sessions/${id}/export?format=${fmt}`)
      const blob = await r.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a'); a.href = url; a.download = `session-${id.slice(0, 8)}.${fmt}`; a.click()
      window.URL.revokeObjectURL(url)
    } catch (e) { console.error('导出失败:', e) }
  }

  const handleAddTag = async (id) => {
    const tag = tagInput.trim(); if (!tag) return
    try {
      const r = await fetch(`${API_BASE}/api/sessions/${id}/tags`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tags: [tag] }) })
      if (r.ok) { setTagInput(''); loadSessions(); if (selectedSession?.id === id) handleSelectSession({ id }) }
    } catch (e) { console.error('添加标签失败:', e) }
  }

  const handleRemoveTag = async (id, tag) => {
    try {
      const r = await fetch(`${API_BASE}/api/sessions/${id}/tags`, { method: 'DELETE', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tags: [tag] }) })
      if (r.ok) { loadSessions(); if (selectedSession?.id === id) handleSelectSession({ id }) }
    } catch (e) { console.error('移除标签失败:', e) }
  }

  const handleSaveNote = async (id) => {
    try {
      const r = await fetch(`${API_BASE}/api/sessions/${id}/note`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ note: noteInput }) })
      if (r.ok) { setShowNoteEditor(false); loadSessions(); if (selectedSession) setSelectedSession(prev => ({ ...prev, note: noteInput })) }
    } catch (e) { console.error('保存备注失败:', e) }
  }

  const handleTagFilter = (tag) => setSelectedTags(prev => prev.includes(tag) ? prev.filter(t => t !== tag) : [...prev, tag])

  const toggleSelect = (id) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }

  const toggleSelectAll = () => {
    if (selectedIds.size === filteredSessions.length) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(filteredSessions.map(s => s.id)))
    }
  }

  const filteredSessions = sessions.filter(s => selectedTags.length === 0 || s.tags?.some(t => selectedTags.includes(t)))

  const formatTime = (ts) => {
    if (!ts) return '未知'
    try { const d = new Date(ts); return d.toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' }) + ' ' + d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) }
    catch { return ts }
  }

  const formatProject = (name) => {
    if (!name) return '未知项目'
    const parts = name.split('-').filter(Boolean)
    return parts.length > 3 ? (parts.slice(3).join('-') || name) : (parts[parts.length - 1] || name)
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50/30 to-indigo-50/40">
      <div className="max-w-7xl mx-auto px-4 py-8">
        {/* 头部 */}
        <header className="mb-8">
          <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm">
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-3xl font-heading font-bold text-slate-800 mb-1 flex items-center gap-3">
                  <MessageSquare className="w-8 h-8 text-blue-600" /> Session Manager
                </h1>
                <p className="text-slate-500 text-sm">Claude Code 会话管理系统</p>
              </div>
              {stats && (
                <div className="text-right hidden sm:block">
                  <div className="text-3xl font-bold text-blue-600">{stats.total || total}</div>
                  <div className="text-sm text-slate-400">总会话数</div>
                </div>
              )}
            </div>
          </div>
        </header>

        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 mb-8">
          <div className="lg:col-span-3">
            <div className="bg-white rounded-2xl p-6 border border-slate-200 shadow-sm">
              {/* 搜索栏 + 操作按钮 */}
              <div className="flex gap-3 mb-4">
                <div className="flex-1 relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
                  <input type="text" placeholder="搜索会话内容..." value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)}
                    className="w-full pl-10 pr-4 py-3 bg-slate-50 border border-slate-200 rounded-xl text-slate-800 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/30 focus:border-blue-400 transition-all" />
                </div>
                <button onClick={() => { setSelectMode(!selectMode); setSelectedIds(new Set()) }}
                  className={`px-4 py-3 rounded-xl transition-all flex items-center gap-2 cursor-pointer border font-medium text-sm ${selectMode ? 'bg-orange-500 text-white border-orange-500' : 'bg-slate-50 text-slate-600 border-slate-200 hover:bg-slate-100'}`}>
                  <CheckSquare className="w-4 h-4" />
                  <span className="hidden sm:inline">多选</span>
                </button>
                <button onClick={() => setShowStats(!showStats)}
                  className={`px-4 py-3 rounded-xl transition-all flex items-center gap-2 cursor-pointer border font-medium text-sm ${showStats ? 'bg-blue-600 text-white border-blue-600' : 'bg-slate-50 text-slate-600 border-slate-200 hover:bg-slate-100'}`}>
                  <BarChart3 className="w-4 h-4" />
                  <span className="hidden sm:inline">统计</span>
                </button>
              </div>

              {/* 多选操作栏 */}
              {selectMode && (
                <div className="flex items-center gap-3 mb-4 p-3 bg-orange-50 border border-orange-200 rounded-xl">
                  <button onClick={toggleSelectAll} className="text-sm text-orange-700 hover:text-orange-900 cursor-pointer font-medium flex items-center gap-1">
                    {selectedIds.size === filteredSessions.length && filteredSessions.length > 0 ? <CheckSquare className="w-4 h-4" /> : <Square className="w-4 h-4" />}
                    {selectedIds.size === filteredSessions.length && filteredSessions.length > 0 ? '取消全选' : '全选'}
                  </button>
                  <span className="text-sm text-orange-600">已选 {selectedIds.size} 项</span>
                  <div className="flex-1" />
                  <button onClick={() => handleBatchExport('md')} disabled={selectedIds.size === 0}
                    className="px-3 py-1.5 bg-blue-500 text-white rounded-lg text-sm cursor-pointer hover:bg-blue-600 disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1 transition-colors">
                    <Download className="w-3.5 h-3.5" /> 导出
                  </button>
                  <button onClick={handleBatchDelete} disabled={selectedIds.size === 0}
                    className="px-3 py-1.5 bg-red-500 text-white rounded-lg text-sm cursor-pointer hover:bg-red-600 disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1 transition-colors">
                    <Trash2 className="w-3.5 h-3.5" /> 删除
                  </button>
                </div>
              )}

              {/* 标签筛选 */}
              {selectedTags.length > 0 && (
                <div className="flex flex-wrap gap-2 mb-4">
                  <span className="text-sm text-slate-400 py-1">筛选:</span>
                  {selectedTags.map(tag => (
                    <span key={tag} className="px-3 py-1 bg-blue-50 text-blue-600 border border-blue-200 rounded-lg text-sm flex items-center gap-2 cursor-pointer hover:bg-blue-100 transition-colors" onClick={() => handleTagFilter(tag)}>
                      <Tag className="w-3 h-3" />{tag}<X className="w-3 h-3" />
                    </span>
                  ))}
                  <button onClick={() => setSelectedTags([])} className="px-3 py-1 text-slate-400 text-sm hover:text-slate-600 cursor-pointer">清除</button>
                </div>
              )}

              {/* 信息栏 */}
              {!loading && total > 0 && (
                <div className="text-xs text-slate-400 mb-3">
                  共 {total} 个会话，第 {page}/{totalPages} 页
                </div>
              )}

              {/* 会话列表 */}
              {loading ? (
                <div className="text-center py-16"><Loader2 className="w-8 h-8 text-blue-500 animate-spin mx-auto mb-3" /><div className="text-slate-400">加载中...</div></div>
              ) : filteredSessions.length === 0 ? (
                <div className="text-center py-16"><MessageSquare className="w-12 h-12 text-slate-300 mx-auto mb-3" /><div className="text-slate-400">{searchTerm ? '未找到匹配的会话' : '暂无会话记录'}</div></div>
              ) : (
                <div className="space-y-2">
                  {filteredSessions.map(session => (
                    <div key={session.id}
                      className={`group rounded-xl p-4 border transition-all cursor-pointer ${selectedIds.has(session.id)
                        ? 'bg-blue-50 border-blue-300 shadow-sm shadow-blue-100'
                        : 'bg-white border-slate-150 hover:border-blue-200 hover:shadow-md hover:shadow-blue-50'
                        }`}
                      onClick={() => handleSelectSession(session)}>
                      <div className="flex items-start gap-3">
                        {/* 多选复选框 */}
                        {selectMode && (
                          <div className="pt-0.5 flex-shrink-0" onClick={(e) => { e.stopPropagation(); toggleSelect(session.id) }}>
                            {selectedIds.has(session.id)
                              ? <CheckSquare className="w-5 h-5 text-blue-600" />
                              : <Square className="w-5 h-5 text-slate-300 hover:text-slate-500" />
                            }
                          </div>
                        )}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-start justify-between mb-1.5">
                            <h3 className="text-base font-heading font-semibold text-slate-800 truncate pr-4">{session.title || '未命名会话'}</h3>
                            {!selectMode && (
                              <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
                                <button onClick={(e) => { e.stopPropagation(); handleExport(session.id) }} className="p-2 hover:bg-slate-100 rounded-lg cursor-pointer" title="导出"><Download className="w-4 h-4 text-slate-400" /></button>
                                <button onClick={(e) => { e.stopPropagation(); handleDelete(session.id) }} className="p-2 hover:bg-red-50 rounded-lg cursor-pointer" title="删除"><Trash2 className="w-4 h-4 text-slate-400 hover:text-red-500" /></button>
                              </div>
                            )}
                          </div>
                          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-400">
                            <span className="flex items-center gap-1"><Calendar className="w-3.5 h-3.5" />{formatTime(session.created_at)}</span>
                            <span className="flex items-center gap-1"><MessageSquare className="w-3.5 h-3.5" />{session.message_count} 条消息</span>
                            <span className="flex items-center gap-1"><FolderOpen className="w-3.5 h-3.5" />{formatProject(session.project)}</span>
                          </div>
                          {session.tags?.length > 0 && (
                            <div className="flex flex-wrap gap-1.5 mt-2">
                              {session.tags.map(tag => (<span key={tag} onClick={(e) => { e.stopPropagation(); handleTagFilter(tag) }} className="px-2 py-0.5 bg-blue-50 text-blue-600 border border-blue-100 rounded text-xs cursor-pointer hover:bg-blue-100">{tag}</span>))}
                            </div>
                          )}
                          {session.note && (<p className="mt-2 text-xs text-slate-400 italic flex items-center gap-1"><StickyNote className="w-3 h-3" />{session.note}</p>)}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* 分页 */}
              {!searchTerm && <Pagination page={page} totalPages={totalPages} onPageChange={handlePageChange} />}
            </div>
          </div>

          {/* 侧边栏统计 */}
          <div className="lg:col-span-1 space-y-6">
            {showStats && stats && (
              <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm">
                <h2 className="text-lg font-heading font-semibold text-slate-700 mb-4 flex items-center gap-2"><BarChart3 className="w-5 h-5 text-blue-600" />统计信息</h2>
                <div className="space-y-4">
                  <div className="bg-gradient-to-r from-blue-50 to-indigo-50 rounded-xl p-4 border border-blue-100">
                    <div className="text-3xl font-bold text-blue-600 mb-1">{stats.total}</div>
                    <div className="text-sm text-slate-500">总会话数</div>
                  </div>
                  {stats.by_project && Object.keys(stats.by_project).length > 0 && (
                    <div className="bg-slate-50 rounded-xl p-4 border border-slate-100">
                      <div className="text-sm font-semibold text-slate-600 mb-3 flex items-center gap-1.5"><FolderOpen className="w-4 h-4 text-slate-400" /> 按项目</div>
                      <div className="space-y-2">{Object.entries(stats.by_project).slice(0, 8).map(([p, c]) => (<div key={p} className="flex justify-between text-sm"><span className="text-slate-600 truncate mr-2" title={p}>{formatProject(p)}</span><span className="text-slate-400 font-mono">{c}</span></div>))}</div>
                    </div>
                  )}
                  {stats.by_month && Object.keys(stats.by_month).length > 0 && (
                    <div className="bg-slate-50 rounded-xl p-4 border border-slate-100">
                      <div className="text-sm font-semibold text-slate-600 mb-3 flex items-center gap-1.5"><Clock className="w-4 h-4 text-slate-400" /> 按月份</div>
                      <div className="space-y-2">{Object.entries(stats.by_month).slice(0, 6).map(([m, c]) => (<div key={m} className="flex justify-between text-sm"><span className="text-slate-600">{m}</span><span className="text-slate-400 font-mono">{c}</span></div>))}</div>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* 会话详情弹窗 */}
        {selectedSession && (
          <div className="fixed inset-0 bg-black/30 backdrop-blur-sm flex items-center justify-center p-4 z-50" onClick={(e) => { if (e.target === e.currentTarget) setSelectedSession(null) }}>
            <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl max-w-4xl w-full max-h-[85vh] flex flex-col">
              <div className="p-6 border-b border-slate-100 flex-shrink-0">
                <div className="flex justify-between items-start">
                  <div className="flex-1 min-w-0 mr-4">
                    <h2 className="text-xl font-heading font-bold text-slate-800 truncate mb-2">{selectedSession.title || '会话详情'}</h2>
                    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-400">
                      <span className="flex items-center gap-1"><Calendar className="w-3.5 h-3.5" /> {formatTime(selectedSession.created_at)}</span>
                      <span className="flex items-center gap-1"><FolderOpen className="w-3.5 h-3.5" /> {formatProject(selectedSession.project)}</span>
                      <span className="flex items-center gap-1"><MessageSquare className="w-3.5 h-3.5" /> {selectedSession.message_count} 条消息</span>
                    </div>
                    {/* 完整 Session ID + 复制 + resume 提示 */}
                    <div className="mt-2 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 space-y-1.5">
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-slate-500 flex-shrink-0">Session ID:</span>
                        <code className="text-xs font-mono text-slate-700 select-all break-all">{selectedSession.id}</code>
                        <button
                          onClick={() => { navigator.clipboard.writeText(selectedSession.id); }}
                          className="flex-shrink-0 px-2 py-0.5 text-xs bg-blue-50 text-blue-600 border border-blue-200 rounded hover:bg-blue-100 cursor-pointer transition-colors"
                          title="复制 Session ID"
                        >复制</button>
                      </div>
                      {selectedSession.project_path && selectedSession.project_path !== selectedSession.project && (
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-slate-500 flex-shrink-0">项目路径:</span>
                          <code className="text-xs font-mono text-slate-600 truncate" title={selectedSession.project_path}>{selectedSession.project_path}</code>
                        </div>
                      )}
                      <div className="flex items-center gap-2 pt-1 border-t border-slate-200">
                        <span className="text-xs text-slate-400">💡 恢复此会话:</span>
                        <button
                          onClick={() => {
                            const pp = selectedSession.project_path && selectedSession.project_path !== selectedSession.project
                              ? selectedSession.project_path : null
                            const cmd = pp
                              ? `cd "${pp}" && claude --resume ${selectedSession.id}`
                              : `claude --resume ${selectedSession.id}`
                            navigator.clipboard.writeText(cmd)
                          }}
                          className="flex-shrink-0 px-2 py-0.5 text-xs bg-emerald-50 text-emerald-700 border border-emerald-200 rounded hover:bg-emerald-100 cursor-pointer transition-colors"
                        >📋 复制 resume 命令</button>
                      </div>
                      <code className="block text-xs font-mono text-slate-600 bg-slate-100 px-2 py-1 rounded select-all break-all">
                        {selectedSession.project_path && selectedSession.project_path !== selectedSession.project
                          ? `cd "${selectedSession.project_path}" && claude --resume ${selectedSession.id}`
                          : `claude --resume ${selectedSession.id}`
                        }
                      </code>
                    </div>
                    <div className="flex flex-wrap items-center gap-1.5 mt-3">
                      {selectedSession.tags?.map(tag => (
                        <span key={tag} className="px-2 py-0.5 bg-blue-50 text-blue-600 border border-blue-100 rounded text-xs cursor-pointer hover:bg-red-50 hover:text-red-500 hover:border-red-200 transition-colors group" onClick={() => handleRemoveTag(selectedSession.id, tag)} title="点击移除">
                          {tag}<X className="w-2.5 h-2.5 inline ml-1 opacity-0 group-hover:opacity-100" />
                        </span>
                      ))}
                      {showTagEditor ? (
                        <div className="flex items-center gap-1">
                          <input type="text" value={tagInput} onChange={(e) => setTagInput(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') handleAddTag(selectedSession.id); if (e.key === 'Escape') setShowTagEditor(false) }} placeholder="标签名" className="px-2 py-0.5 bg-slate-50 border border-slate-200 rounded text-xs text-slate-700 w-20 focus:outline-none focus:ring-1 focus:ring-blue-400" autoFocus />
                          <button onClick={() => handleAddTag(selectedSession.id)} className="px-2 py-0.5 bg-blue-50 text-blue-600 rounded text-xs cursor-pointer hover:bg-blue-100">添加</button>
                        </div>
                      ) : (
                        <button onClick={() => setShowTagEditor(true)} className="px-2 py-0.5 border border-dashed border-slate-300 rounded text-xs text-slate-400 cursor-pointer hover:text-blue-600 hover:border-blue-300 flex items-center gap-0.5"><Plus className="w-3 h-3" /> 标签</button>
                      )}
                    </div>
                    {showNoteEditor ? (
                      <div className="mt-3 flex items-center gap-2">
                        <input type="text" value={noteInput} onChange={(e) => setNoteInput(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') handleSaveNote(selectedSession.id); if (e.key === 'Escape') setShowNoteEditor(false) }} placeholder="输入备注..." className="flex-1 px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg text-sm text-slate-700 focus:outline-none focus:ring-1 focus:ring-blue-400" autoFocus />
                        <button onClick={() => handleSaveNote(selectedSession.id)} className="px-3 py-1.5 bg-blue-50 text-blue-600 rounded-lg text-sm cursor-pointer hover:bg-blue-100">保存</button>
                      </div>
                    ) : (
                      <div className="mt-2 text-xs text-slate-400 italic cursor-pointer hover:text-blue-500 flex items-center gap-1" onClick={() => { setNoteInput(selectedSession.note || ''); setShowNoteEditor(true) }}>
                        <StickyNote className="w-3 h-3" />{selectedSession.note || '点击添加备注...'}
                      </div>
                    )}
                  </div>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    <div className="relative group/export">
                      <button className="p-2 hover:bg-slate-100 rounded-lg cursor-pointer" title="导出"><Download className="w-5 h-5 text-slate-400" /></button>
                      <div className="absolute right-0 top-full mt-1 bg-white border border-slate-200 rounded-lg p-1 hidden group-hover/export:block min-w-[100px] z-10 shadow-lg">
                        {['md', 'json', 'txt'].map(fmt => (<button key={fmt} onClick={() => handleExport(selectedSession.id, fmt)} className="w-full px-3 py-1.5 text-left text-sm text-slate-600 hover:bg-slate-50 rounded cursor-pointer">{fmt.toUpperCase()}</button>))}
                      </div>
                    </div>
                    <button onClick={() => { setSelectedSession(null); setShowNoteEditor(false); setShowTagEditor(false) }} className="p-2 hover:bg-slate-100 rounded-lg cursor-pointer"><X className="w-5 h-5 text-slate-400" /></button>
                  </div>
                </div>
              </div>

              <div className="flex-1 overflow-y-auto p-6 bg-slate-50/50">
                {detailLoading ? (
                  <div className="text-center py-12"><Loader2 className="w-8 h-8 text-blue-500 animate-spin mx-auto mb-3" /><div className="text-slate-400">加载会话内容...</div></div>
                ) : selectedSession.error ? (
                  <div className="text-center py-12"><div className="text-red-500 mb-2">{selectedSession.error}</div><button onClick={() => handleSelectSession(selectedSession)} className="text-blue-600 text-sm cursor-pointer hover:underline">重试</button></div>
                ) : selectedSession.messages?.length === 0 ? (
                  <div className="text-center py-12 text-slate-400">此会话暂无可显示的消息</div>
                ) : (
                  <div className="space-y-4">
                    {selectedSession.messages?.map((msg, idx) => (
                      <div key={idx} className={`p-4 rounded-xl ${msg.role === 'user' ? 'bg-blue-50 border border-blue-100 ml-0 mr-12' : 'bg-white border border-slate-200 ml-8 mr-0 shadow-sm'}`}>
                        <div className="flex items-center justify-between mb-2">
                          <div className={`text-xs font-semibold ${msg.role === 'user' ? 'text-blue-600' : 'text-emerald-600'}`}>
                            {msg.role === 'user' ? '👤 用户' : '🤖 Claude'}
                          </div>
                          {msg.timestamp && <div className="text-xs text-slate-400">{formatTime(msg.timestamp)}</div>}
                        </div>
                        {msg.blocks && msg.blocks.length > 0 ? <MessageBlocks blocks={msg.blocks} /> : <div className="text-sm text-slate-700 whitespace-pre-wrap break-words">{msg.content}</div>}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default App

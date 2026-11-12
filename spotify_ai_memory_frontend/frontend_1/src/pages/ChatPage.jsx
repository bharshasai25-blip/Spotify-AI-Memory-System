import { useEffect, useMemo, useRef, useState } from 'react'
import ChatPanel from '../components/ChatPanel'
import { apiFetch } from '../api/client'

function newConversationId() {
  return globalThis.crypto?.randomUUID?.() || `conversation-${Date.now()}-${Math.random().toString(36).slice(2)}`
}
function ChatPage({ session }) {
  const storageKey = useMemo(() => `spotify_ai_conversation_${session?.subject_id || 'guest'}`, [session?.subject_id])
  const [conversationId, setConversationId] = useState(() => localStorage.getItem(storageKey) || newConversationId())
  const messagesStorageKey = `spotify_ai_messages_${session?.subject_id || 'guest'}_${conversationId}`
  const [chatQuery, setChatQuery] = useState('')
  const [messages, setMessages] = useState(() => { try { return JSON.parse(localStorage.getItem(messagesStorageKey) || '[]') } catch { return [] } })
  const [chatLoading, setChatLoading] = useState(false)
  const [historyLoading, setHistoryLoading] = useState(true)
  const [memoryActionLoading, setMemoryActionLoading] = useState('')
  const [memoryActionError, setMemoryActionError] = useState('')
  const endOfMessagesRef = useRef(null)

  useEffect(() => {
    localStorage.setItem(storageKey, conversationId)
  }, [storageKey, conversationId])

  useEffect(() => {
    localStorage.setItem(messagesStorageKey, JSON.stringify(messages))
  }, [messagesStorageKey, messages])

  useEffect(() => {
    let cancelled = false
    setHistoryLoading(true)
    apiFetch(`/v1/chat/history?conversation_id=${encodeURIComponent(conversationId)}`)
      .then((result) => {
        if (!cancelled && result.messages?.length) setMessages((result.messages || []).map((message) => ({
          id: message.message_id,
          role: message.role,
          content: message.content,
          createdAt: message.created_at,
          metadata: message.metadata || {},
          response: message.metadata?.response_metadata ? { response_metadata: message.metadata.response_metadata } : null,
        })))
      })
      .catch((error) => {
        if (!cancelled) setMemoryActionError(`Could not restore chat history: ${error.message}`)
      })
      .finally(() => { if (!cancelled) setHistoryLoading(false) })
    return () => { cancelled = true }
  }, [conversationId])

  useEffect(() => {
    endOfMessagesRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, chatLoading])

  const ensureMemoryConsent = async () => {
    if (!session) throw new Error('You must be signed in to change a memory.')
    const key = `spotify_ai_memory_consent_${session.subject_id}`
    if (localStorage.getItem(key) === 'false') throw new Error('Memory consent is disabled. Enable it in the top-right account controls before changing a memory.')
    if (localStorage.getItem(key) === 'true') return
    throw new Error('Please enable memory consent in the top-right account controls before changing a memory.')
  }

  const handleEdit = async (memoryId) => {
    const correctedStatement = window.prompt(`Edit preference for memory ${memoryId}:`)
    if (!correctedStatement?.trim()) return
    setMemoryActionLoading(memoryId); setMemoryActionError('')
    try {
      await ensureMemoryConsent()
      const result = await apiFetch(`/v1/memories/${encodeURIComponent(memoryId)}`, { method: 'PATCH', body: JSON.stringify({ schema_version: '1.0', corrected_statement: correctedStatement.trim(), reason: 'Updated from chat.', metadata: { source: 'react-app' } }) })
      setMessages((previous) => previous.map((message) => message.response ? { ...message, response: { ...message.response, memory_references: (message.response.memory_references || []).map((reference) => reference.memory_id === memoryId ? { ...reference, memory_id: result.corrected_memory_id || memoryId, memory_text: correctedStatement.trim() } : reference) } } : message))
    } catch (error) { setMemoryActionError(error.message) } finally { setMemoryActionLoading('') }
  }

  const handleDelete = async (memoryId) => {
    if (!window.confirm('Delete this preference from memory?')) return
    setMemoryActionLoading(memoryId); setMemoryActionError('')
    try {
      await apiFetch(`/v1/memories/${encodeURIComponent(memoryId)}`, { method: 'DELETE', body: JSON.stringify({ schema_version: '1.0', reason: 'Deleted from chat.', metadata: { source: 'react-app' } }) })
      setMessages((previous) => previous.map((message) => message.response ? { ...message, response: { ...message.response, memory_references: (message.response.memory_references || []).filter((reference) => reference.memory_id !== memoryId) } } : message))
    } catch (error) { setMemoryActionError(error.message) } finally { setMemoryActionLoading('') }
  }

  const handleSubmit = async (event) => {
    event.preventDefault()
    const query = chatQuery.trim()
    if (!query || chatLoading) return
    const userMessage = { id: newConversationId(), role: 'user', content: query, createdAt: new Date().toISOString() }
    setMessages((previous) => [...previous, userMessage])
    setChatQuery(''); setChatLoading(true); setMemoryActionError('')
    try {
      const result = await apiFetch('/v1/chat', { method: 'POST', body: JSON.stringify({ schema_version: '1.0', query, surface: 'web', locale: 'en-US', requested_at: new Date().toISOString(), max_response_characters: 5000, include_memory_references: true, conversation_id: conversationId, metadata: { source: 'react-app' } }) })
      setMessages((previous) => [...previous, { id: result.response?.response_id || newConversationId(), role: 'assistant', content: result.response?.response_text || 'I could not generate a response.', createdAt: result.response?.generated_at || new Date().toISOString(), response: result.response || null }])
      if (result.conversation_id && result.conversation_id !== conversationId) setConversationId(result.conversation_id)
    } catch (error) {
      setMessages((previous) => [...previous, { id: newConversationId(), role: 'assistant', content: `I couldn't complete that request: ${error.message}`, error: true, createdAt: new Date().toISOString() }])
    } finally { setChatLoading(false) }
  }


  const handleConfirmSelection = async (selectionToken, selectedEntities, messageId) => {
    if (!selectionToken || !selectedEntities?.length || chatLoading) return
    setMemoryActionLoading(`selection:${messageId}`); setMemoryActionError('')
    try {
      const result = await apiFetch('/v1/musicbrainz/selection/confirm', { method: 'POST', body: JSON.stringify({ schema_version: '1.0', selection_token: selectionToken, selected_entities: selectedEntities }) })
      const summary = result.message || (result.memory_created ? 'Selection confirmed and saved.' : 'Selection confirmed, but no memory was saved.')
      setMessages((previous) => previous.map((message) => message.id === messageId ? { ...message, content: summary, response: { ...(message.response || {}), response_metadata: { ...(message.response?.response_metadata || {}), musicbrainz_selection: { ...(message.response?.response_metadata?.musicbrainz_selection || {}), completed: Boolean(result.memory_created), selected_entities: selectedEntities, confirmation: result } } } } : message))
      if (!result.memory_created && /consent|opt in|paused/i.test(summary)) setMemoryActionError(summary)
    } catch (error) { setMemoryActionError(`Could not confirm the recording selection: ${error.message}`) } finally { setMemoryActionLoading('') }
  }

  const handleNewConversation = () => {
    const nextId = newConversationId()
    setConversationId(nextId)
    setMessages([])
    setMemoryActionError('')
  }

  return <ChatPanel chatQuery={chatQuery} setChatQuery={setChatQuery} messages={messages} chatLoading={chatLoading} historyLoading={historyLoading} onSubmit={handleSubmit} session={session} memoryActionLoading={memoryActionLoading} memoryActionError={memoryActionError} onEdit={handleEdit} onDelete={handleDelete} onNewConversation={handleNewConversation} onConfirmSelection={handleConfirmSelection} endOfMessagesRef={endOfMessagesRef} />
}
export default ChatPage
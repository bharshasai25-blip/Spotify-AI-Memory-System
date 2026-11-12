import { useState } from 'react'
import { Link } from 'react-router-dom'

function formatDuration(value) {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) return ''
  const totalSeconds = Math.round(value / 1000)
  return `${Math.floor(totalSeconds / 60)}:${String(totalSeconds % 60).padStart(2, '0')}`
}
function MusicBrainzCandidateSelector({ selection, messageId, loading, onConfirm }) {
  const [selected, setSelected] = useState({})
  const groups = selection?.groups?.length ? selection.groups : [{ entity_type: selection?.entity_type || 'track', entity_name: selection?.entity_name || '', candidates: selection?.candidates || [] }]
  if (!groups.some(group => group.candidates?.length) || selection.completed) return null
  const toggle = (groupIndex, mbid) => setSelected(previous => {
    const key = `${groupIndex}:${mbid}`
    return { ...previous, [key]: !previous[key] }
  })
  const selectedEntities = groups.flatMap((group, groupIndex) => (group.candidates || []).filter(candidate => selected[`${groupIndex}:${candidate.mbid}`]).map(candidate => ({ entity_type: group.entity_type || 'track', mbid: candidate.mbid })))
  return <div className="mt-4 border-t border-white/10 pt-3">
    <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">Confirm the entities you mean</p>
    <p className="mb-3 text-xs text-muted">Choose one or more results in each group. Nothing is saved until you confirm.</p>
    <div className="space-y-4">{groups.map((group, groupIndex) => <section key={`${group.entity_type}:${group.entity_name}:${groupIndex}`}><p className="mb-2 text-sm font-semibold text-white">{group.entity_name || `Entity ${groupIndex + 1}`} <span className="text-xs font-normal capitalize text-muted">({group.entity_type || 'music'})</span></p><div className="space-y-2">{(group.candidates || []).map(candidate => <label key={`${groupIndex}:${candidate.mbid}`} className={`flex cursor-pointer gap-3 rounded-xl border p-3 ${selected[`${groupIndex}:${candidate.mbid}`] ? 'border-spotify bg-spotify/10' : 'border-white/10 bg-black/20'}`}>
      <input type="checkbox" checked={Boolean(selected[`${groupIndex}:${candidate.mbid}`])} onChange={() => toggle(groupIndex, candidate.mbid)} className="mt-1 accent-spotify" disabled={loading} />
      <span className="min-w-0 flex-1"><span className="block text-sm font-semibold">{candidate.name || group.entity_name}</span>
        {candidate.artist_names?.length ? <span className="mt-1 block text-xs text-muted">Artist: {candidate.artist_names.join(', ')}</span> : null}
        {candidate.release_names?.length ? <span className="mt-1 block text-xs text-muted">Release: {candidate.release_names.slice(0, 2).join(', ')}</span> : null}
        {candidate.disambiguation ? <span className="mt-1 block text-xs text-muted">{candidate.disambiguation}</span> : null}
        {formatDuration(candidate.length_ms) ? <span className="mt-1 block text-xs text-muted">Duration: {formatDuration(candidate.length_ms)}</span> : null}
        {candidate.spotify_url ? <a href={candidate.spotify_url} target="_blank" rel="noreferrer" onClick={event => event.stopPropagation()} className="mt-2 inline-block text-xs font-semibold text-spotify-light hover:underline">{candidate.spotify_url_label || (candidate.spotify_url_type === 'track' ? 'Play on Spotify' : 'Search on Spotify')} ↗</a> : null}
      </span>
    </label>)}</div></section>)}</div>
    <button type="button" onClick={() => onConfirm(selection.selection_token, selectedEntities, messageId)} disabled={loading || selectedEntities.length === 0} className="button-primary mt-3 w-full">{loading ? 'Confirming selection…' : `Confirm ${selectedEntities.length ? selectedEntities.length + ' selection' + (selectedEntities.length > 1 ? 's' : '') : 'selection'}`}</button>
  </div>
}
function ChatPanel({ chatQuery, setChatQuery, messages, chatLoading, historyLoading, onSubmit, session, memoryActionLoading, memoryActionError, onEdit, onDelete, onNewConversation, onConfirmSelection, endOfMessagesRef }) {
  return <section className="panel flex min-h-[76vh] flex-col overflow-hidden">
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 px-5 py-4 sm:px-6">
      <div><p className="eyebrow">Personal music assistant</p><h2 className="mt-1 text-xl font-semibold text-white">Your conversation</h2><p className="mt-1 text-sm text-muted">Chat history is saved to your account.</p></div>
      <button type="button" onClick={onNewConversation} className="button-secondary">New conversation</button>
    </div>
    <div className="flex-1 space-y-4 overflow-y-auto px-4 py-5 sm:px-6" aria-live="polite">
      {historyLoading ? <p className="text-center text-sm text-muted">Restoring your conversation…</p> : null}
      {!historyLoading && !messages.length ? <div className="mx-auto max-w-lg py-12 text-center"><div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-spotify/15 text-2xl">♫</div><h3 className="mt-4 text-lg font-semibold text-white">What would you like to explore?</h3><p className="mt-2 text-sm text-muted">Ask about your music preferences, memories, artists, or tracks.</p></div> : null}
      {messages.map((message) => <div key={message.id} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
        <article className={`max-w-[92%] rounded-2xl px-4 py-3 sm:max-w-[82%] ${message.role === 'user' ? 'rounded-br-md bg-spotify text-[#07150b]' : 'rounded-bl-md border border-white/10 bg-[#1b1b1b] text-slate-100'}`}>
          <p className="mb-1 text-[11px] font-semibold uppercase tracking-wider opacity-70">{message.role === 'user' ? 'You' : 'Spotify AI'}</p>
          <p className={`whitespace-pre-wrap break-words text-sm leading-6 ${message.error ? 'text-rose-300' : ''}`}>{message.content}</p>
          {message.response?.memory_references?.length ? <div className="mt-4 border-t border-white/10 pt-3"><p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">Related memories</p>{message.response.memory_references.map((reference) => <div key={reference.memory_id} className="mb-2 rounded-xl border border-white/10 bg-black/20 p-3"><p className="text-sm">{reference.memory_text || reference.memory_id}</p><div className="mt-2 flex gap-2"><button type="button" onClick={() => onEdit(reference.memory_id)} disabled={Boolean(memoryActionLoading)} className="button-small">Edit</button><button type="button" onClick={() => onDelete(reference.memory_id)} disabled={Boolean(memoryActionLoading)} className="button-small-danger">Delete</button></div></div>)}</div> : null}
          {message.response?.response_metadata?.musicbrainz_selection ? <MusicBrainzCandidateSelector selection={message.response.response_metadata.musicbrainz_selection} messageId={message.id} loading={memoryActionLoading === `selection:${message.id}`} onConfirm={onConfirmSelection} /> : null}
        </article>
      </div>)}
      {chatLoading ? <div className="flex justify-start"><div className="rounded-2xl rounded-bl-md border border-white/10 bg-[#1b1b1b] px-4 py-3 text-sm text-muted">Thinking…</div></div> : null}
      <div ref={endOfMessagesRef} />
    </div>
    {memoryActionError ? <p className="mx-5 mb-2 text-sm text-rose-300">{memoryActionError} {memoryActionError.includes('consent') ? <Link to="/memory-settings" className="underline">Open Memory Settings</Link> : null}</p> : null}
    <form onSubmit={onSubmit} className="border-t border-white/10 bg-black/20 p-4 sm:p-5"><label htmlFor="chat-query" className="sr-only">Your message</label><div className="flex items-end gap-3"><textarea id="chat-query" value={chatQuery} onChange={(event) => setChatQuery(event.target.value)} rows={2} maxLength={10000} className="field min-h-14 flex-1 resize-y" placeholder="Ask a follow-up or tell me about your music taste…" disabled={!session || chatLoading || historyLoading} /><button type="submit" disabled={!session || chatLoading || historyLoading || !chatQuery.trim()} className="button-primary min-h-14 shrink-0">{chatLoading ? 'Sending…' : 'Send ↗'}</button></div><p className="mt-2 text-xs text-muted">Your transcript is separate from long-term memories. Only governed memory operations update saved preferences.</p></form>
  </section>
}
export default ChatPanel
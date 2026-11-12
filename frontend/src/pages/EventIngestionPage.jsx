import { useCallback, useEffect, useState } from 'react'
import { Link, useOutletContext } from 'react-router-dom'
import { apiFetch } from '../api/client'
import MusicCatalogActions from '../components/MusicCatalogActions'

const emptyAction = { action: 'follow', entity_type: 'artist', name: '', spotify_url: '' }
const emptyRawEvent = { event_type: 'ai_interaction', text: '', metadata: '{"source":"web"}' }
function EventIngestionPage() {
  const { memoryConsent } = useOutletContext()
  const [preference, setPreference] = useState('')
  const [actionForm, setActionForm] = useState(emptyAction)
  const [rawEvent, setRawEvent] = useState(emptyRawEvent)
  const [memories, setMemories] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const loadMemories = useCallback(async () => {
    setLoading(true); setError('')
    try { const result = await apiFetch('/v1/memories'); setMemories(result.memories || []) }
    catch (err) { setError(err.message) }
    finally { setLoading(false) }
  }, [])
  useEffect(() => { Promise.resolve().then(loadMemories) }, [loadMemories])
  const addPreference = async (event) => {
    event.preventDefault()
    if (!memoryConsent) { setError('Opt in to memory saving using the controls in the top-right corner before adding preferences.'); return }
    if (!preference.trim()) return
    setSaving(true); setError(''); setNotice('')
    try {
      const result = await apiFetch('/v1/memories/preferences', { method: 'POST', body: JSON.stringify({ schema_version: '1.0', preference: preference.trim(), surface: 'web', locale: 'en-US', effective_at: new Date().toISOString(), idempotency_key: crypto.randomUUID(), entity: null, context_entities: {}, metadata: { source: 'manual-preference-form' } }) })
      setNotice(result.message || 'Preference submitted successfully.'); setPreference(''); await loadMemories()
    } catch (err) { setError(err.message) } finally { setSaving(false) }
  }
  const submitAction = async (event) => {
    event.preventDefault()
    if (!memoryConsent) { setError('Opt in to memory saving before following artists or saving tracks.'); return }
    if (!actionForm.name.trim()) { setError('Enter an artist or track name.'); return }
    setSaving(true); setError(''); setNotice('')
    const eventType = actionForm.action
    const entityType = eventType === 'follow' ? 'artist' : 'track'
    try {
      const result = await apiFetch('/v1/events', { method: 'POST', body: JSON.stringify({ schema_version: '1.0', event_type: eventType, surface: 'web', locale: 'en-US', text: `${eventType === 'follow' ? 'Follow artist' : 'Save track'}: ${actionForm.name.trim()}`, entity: { entity_type: entityType, name: actionForm.name.trim() }, context_entities: {}, metadata: { source: 'manual-preference-action', spotify_url: actionForm.spotify_url.trim() || null, action: eventType }, idempotency_key: crypto.randomUUID() }) })
      setNotice(`${eventType === 'follow' ? 'Artist follow' : 'Track save'} action submitted. ${result.memory_write_status === 'completed' ? 'Memory pipeline processed the event.' : 'The event was accepted; a long-term memory may require additional evidence.'}`)
      setActionForm(emptyAction); await loadMemories()
    } catch (err) { setError(err.message) } finally { setSaving(false) }
  }
  const submitRawEvent = async (event) => {
    event.preventDefault()
    if (!memoryConsent) { setError('Opt in to memory saving before submitting events.'); return }
    setSaving(true); setError(''); setNotice('')
    try {
      const metadata = JSON.parse(rawEvent.metadata || '{}')
      const result = await apiFetch('/v1/events', { method: 'POST', body: JSON.stringify({ schema_version: '1.0', event_type: rawEvent.event_type, surface: 'web', locale: 'en-US', text: rawEvent.text.trim() || null, entity: null, context_entities: {}, metadata, idempotency_key: crypto.randomUUID() }) })
      setNotice(`Event accepted: ${result.event_id}. ${result.memory_write_status === 'completed' ? 'The memory pipeline processed it.' : 'It may not create a long-term memory until enough evidence is available.'}`)
      setRawEvent(emptyRawEvent); await loadMemories()
    } catch (err) { setError(err.message) } finally { setSaving(false) }
  }
  const editMemory = async (memory) => {
    const updated = window.prompt('Correct this preference:', memory.normalized_fact)
    if (!updated?.trim() || updated.trim() === memory.normalized_fact) return
    if (!memoryConsent) { setError('Opt in to memory saving before correcting a preference.'); return }
    setSaving(true); setError(''); setNotice('')
    try { await apiFetch(`/v1/memories/${encodeURIComponent(memory.memory_id)}`, { method: 'PATCH', body: JSON.stringify({ schema_version: '1.0', corrected_statement: updated.trim(), reason: 'Updated manually from My Preferences.', metadata: { source: 'react-app' } }) }); setNotice('Preference corrected.'); await loadMemories() }
    catch (err) { setError(err.message) } finally { setSaving(false) }
  }
  const deleteMemory = async (memory) => {
    if (!window.confirm(`Delete this preference?\n\n${memory.normalized_fact}`)) return
    setSaving(true); setError(''); setNotice('')
    try { await apiFetch(`/v1/memories/${encodeURIComponent(memory.memory_id)}`, { method: 'DELETE', body: JSON.stringify({ schema_version: '1.0', reason: 'Deleted manually from My Preferences.', metadata: { source: 'react-app' } }) }); setNotice('Preference deleted.'); await loadMemories() }
    catch (err) { setError(err.message) } finally { setSaving(false) }
  }
  return <div className="space-y-6">
    <section className="panel p-5 sm:p-6"><div className="section-heading"><div><p className="eyebrow">PERSONALIZATION</p><h2 className="mt-1 text-xl font-semibold text-white">Manage your preferences</h2><p className="mt-2 max-w-2xl text-sm text-muted">Add a preference in your own words, correct anything that has changed, or remove a saved memory. These actions use your governed memory pipeline.</p></div><span className={`status-pill ${memoryConsent ? 'status-positive' : 'status-muted'}`}>{memoryConsent ? 'Memory enabled' : 'Memory disabled'}</span></div>
      {!memoryConsent ? <p className="mt-4 rounded-xl border border-amber-300/20 bg-amber-300/5 p-3 text-sm text-amber-100">Memory saving is currently disabled. You can enable it in the account controls at the top-right. <Link to="/memory-settings" className="underline">Learn about memory settings</Link>.</p> : null}
      <form onSubmit={addPreference} className="mt-5"><label className="field-label" htmlFor="preference-text">Add a preference</label><textarea id="preference-text" value={preference} onChange={(event) => setPreference(event.target.value)} rows={3} className="field mt-2 w-full" placeholder="For example: I enjoy mellow electronic music and jazz fusion." maxLength={10000}/><div className="mt-3 flex flex-wrap items-center justify-between gap-3"><p className="text-xs text-muted">Be specific if you want a preference linked to an artist, track, or album.</p><button className="button-primary" type="submit" disabled={saving || !preference.trim() || !memoryConsent}>{saving ? 'Saving…' : 'Add preference'}</button></div></form>
    </section>
    <MusicCatalogActions memoryConsent={memoryConsent} />
    <section className="panel p-5 sm:p-6"><p className="eyebrow">MUSIC ACTIONS</p><h2 className="mt-1 text-xl font-semibold text-white">Follow an artist or save a track</h2><p className="mt-2 text-sm text-muted">Record an explicit follow/save action so the existing event pipeline can process it.</p><form onSubmit={submitAction} className="mt-5 grid gap-3 md:grid-cols-2"><div><label className="field-label" htmlFor="music-action">Action</label><select id="music-action" value={actionForm.action} onChange={(event) => setActionForm({ ...actionForm, action: event.target.value, entity_type: event.target.value === 'follow' ? 'artist' : 'track' })} className="field mt-2 w-full"><option value="follow">Follow artist</option><option value="save">Save track</option></select></div><div><label className="field-label" htmlFor="entity-name">{actionForm.action === 'follow' ? 'Artist name' : 'Track name'}</label><input id="entity-name" value={actionForm.name} onChange={(event) => setActionForm({ ...actionForm, name: event.target.value })} className="field mt-2 w-full" placeholder={actionForm.action === 'follow' ? 'Artist name' : 'Track name'} maxLength={300}/></div><div className="md:col-span-2"><label className="field-label" htmlFor="spotify-url">Spotify URL (optional)</label><input id="spotify-url" type="url" value={actionForm.spotify_url} onChange={(event) => setActionForm({ ...actionForm, spotify_url: event.target.value })} className="field mt-2 w-full" placeholder="https://open.spotify.com/…"/></div><div className="md:col-span-2 flex justify-end"><button className="button-secondary" type="submit" disabled={saving || !actionForm.name.trim() || !memoryConsent}>{saving ? 'Submitting…' : actionForm.action === 'follow' ? 'Follow artist' : 'Save track'}</button></div></form></section>
    <section className="panel p-5 sm:p-6"><div className="section-heading"><div><p className="eyebrow">SAVED ITEMS</p><h2 className="mt-1 text-xl font-semibold text-white">Your current preferences</h2></div><button type="button" className="button-secondary" onClick={loadMemories} disabled={loading}>Refresh</button></div>
      {error ? <p className="mt-4 rounded-xl border border-rose-400/20 bg-rose-400/5 p-3 text-sm text-rose-200">{error}</p> : null}{notice ? <p className="mt-4 rounded-xl border border-spotify/20 bg-spotify/5 p-3 text-sm text-spotify-light">{notice}</p> : null}
      {loading ? <p className="mt-5 text-sm text-muted">Loading preferences…</p> : memories.length ? <div className="mt-4 space-y-3">{memories.map((memory) => <article key={memory.memory_id} className="content-row"><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><span className="status-pill">{memory.memory_type}</span><span className="text-xs text-muted">{new Date(memory.created_at).toLocaleDateString()}</span></div><p className="mt-2 text-sm leading-6 text-white">{memory.normalized_fact}</p><p className="mt-1 break-all font-mono text-[10px] text-muted">{memory.memory_id}</p></div><div className="flex shrink-0 gap-2"><button type="button" className="button-small" disabled={saving} onClick={() => editMemory(memory)}>Correct</button><button type="button" className="button-small-danger" disabled={saving} onClick={() => deleteMemory(memory)}>Delete</button></div></article>)}</div> : <p className="mt-5 rounded-xl border border-white/10 p-5 text-sm text-muted">No saved memories found yet. Add an explicit preference above or continue chatting with your assistant.</p>}
    </section>
    <details className="panel p-5"><summary className="cursor-pointer font-semibold text-white">Advanced event ingestion</summary><p className="mt-2 text-sm text-muted">Submit a raw interaction event through the existing event-ingestion API.</p><form onSubmit={submitRawEvent} className="mt-4 space-y-3"><div><label className="field-label" htmlFor="raw-event-type">Event type</label><select id="raw-event-type" className="field mt-2 w-full" value={rawEvent.event_type} onChange={(event) => setRawEvent({ ...rawEvent, event_type: event.target.value })}>{['ai_interaction','playback','save','follow','skip','explicit_preference'].map((type) => <option key={type} value={type}>{type}</option>)}</select></div><div><label className="field-label" htmlFor="raw-event-text">Event text</label><textarea id="raw-event-text" className="field mt-2 w-full" rows={3} value={rawEvent.text} onChange={(event) => setRawEvent({ ...rawEvent, text: event.target.value })} placeholder="Describe the interaction or event" /></div><div><label className="field-label" htmlFor="raw-event-metadata">Metadata JSON</label><textarea id="raw-event-metadata" className="field mt-2 w-full font-mono text-xs" rows={2} value={rawEvent.metadata} onChange={(event) => setRawEvent({ ...rawEvent, metadata: event.target.value })} /></div><button type="submit" className="button-secondary" disabled={saving || !memoryConsent}>Submit event</button></form></details>
  </div>
}
export default EventIngestionPage

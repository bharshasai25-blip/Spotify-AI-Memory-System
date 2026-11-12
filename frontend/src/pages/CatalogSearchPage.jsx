import { useCallback, useEffect, useState } from 'react'
import { apiFetch } from '../api/client'

function formatDuration(value) {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) return ''
  const seconds = Math.round(value / 1000)
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}
function statusButton(active, activeLabel, inactiveLabel, removeLabel, onToggle, busy) {
  if (active) return <div className="flex flex-wrap items-center gap-2"><span className="status-pill status-positive">{activeLabel}</span><button className="button-small-danger" disabled={busy} onClick={onToggle}>{removeLabel}</button></div>
  return <button className="button-small" disabled={busy} onClick={onToggle}>{inactiveLabel}</button>
}
function EntityActions({ item, busy, onAction }) {
  return <div className="mt-4 flex flex-wrap gap-2">
    {item.entity_type === 'artist' ? statusButton(item.is_followed, 'Following', 'Follow', 'Unfollow', () => onAction(item, 'follow', !item.is_followed), busy) : null}
    {item.entity_type === 'track' ? statusButton(item.is_saved, 'Saved', 'Save track', 'Remove from saved tracks', () => onAction(item, 'save', !item.is_saved), busy) : null}
    {item.entity_type === 'album' ? statusButton(item.is_saved, 'Saved', 'Save album', 'Remove from saved albums', () => onAction(item, 'save', !item.is_saved), busy) : null}
    {['artist', 'track', 'album'].includes(item.entity_type) ? statusButton(item.is_preferred, 'Added to preferred list', 'Add as preference', 'Remove from preferred list', () => onAction(item, 'preference', !item.is_preferred), busy) : null}
  </div>
}
export default function CatalogSearchPage() {
  const [query, setQuery] = useState('')
  const [type, setType] = useState('all')
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(false)
  const [searched, setSearched] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [busyId, setBusyId] = useState('')
  const [selectedEntityId, setSelectedEntityId] = useState('')
  const search = useCallback(async (term = query, kind = type) => {
    if (!term.trim()) { setItems([]); setSearched(false); return }
    setLoading(true); setError(''); setNotice('')
    try {
      const result = await apiFetch(`/v1/catalog/search?query=${encodeURIComponent(term.trim())}&entity_type=${encodeURIComponent(kind)}&limit=50`)
      setItems(result.results || []); setSearched(true)
    } catch (err) { setError(err.message) } finally { setLoading(false) }
  }, [query, type])
  useEffect(() => { if (query.trim().length >= 2) { const timer = setTimeout(() => search(query, type), 350); return () => clearTimeout(timer) } }, [query, type, search])
  const updateAction = async (item, action, active) => {
    const subjectId = (() => { try { return JSON.parse(localStorage.getItem('spotify_ai_session') || 'null')?.subject_id || '' } catch { return '' } })()
    if (localStorage.getItem(`spotify_ai_memory_consent_${subjectId}`) !== 'true') { setError('Enable memory consent in the account controls before changing music lists.'); return }
    const key = `${item.entity_id}:${action}`; setBusyId(key); setError(''); setNotice('')
    try {
      const result = await apiFetch('/v1/catalog/actions', { method: 'POST', body: JSON.stringify({ entity_id: item.entity_id, entity_type: item.entity_type, mbid: item.mbid || null, name: item.name, artist_name: item.artist_names?.join(', ') || null, action, active }) })
      setItems(previous => previous.map(candidate => candidate.entity_id === item.entity_id ? { ...candidate, is_followed: result.actions.follow, is_saved: result.actions.save, is_preferred: result.actions.preference, spotify_url: result.spotify_url || candidate.spotify_url, spotify_url_type: result.spotify_url_type || candidate.spotify_url_type, spotify_url_label: result.spotify_url_label || candidate.spotify_url_label, already_cataloged: true } : candidate))
      setNotice(`${item.name}: ${active ? ({follow:'followed',save:'saved',preference:'added to your preferred list'}[action]) : ({follow:'unfollowed',save:item.entity_type === 'album' ? 'removed from saved albums' : 'removed from saved tracks',preference:'removed from your preferred list'}[action])}.`)
    } catch (err) { setError(err.message) } finally { setBusyId('') }
  }
  return <div className="space-y-5">
    <section className="hero-panel"><div><p className="eyebrow">MUSIC CATALOG</p><h2 className="mt-2 text-2xl font-bold text-white sm:text-3xl">Search artists and tracks</h2><p className="mt-3 max-w-2xl text-sm leading-6 text-muted">Search your saved catalog and MusicBrainz results together. New MusicBrainz results are cataloged only when you take an action on them.</p></div></section>
    <section className="panel p-4 sm:p-5"><form className="grid gap-3 sm:grid-cols-[1fr_180px_auto]" onSubmit={event => { event.preventDefault(); search() }}><label className="sr-only" htmlFor="catalog-query">Search music catalog</label><input id="catalog-query" className="field w-full" value={query} onChange={event => setQuery(event.target.value)} placeholder="Search an artist, track, or album…" /><label className="sr-only" htmlFor="catalog-type">Entity type</label><select id="catalog-type" className="field" value={type} onChange={event => setType(event.target.value)}><option value="all">All entities</option><option value="artist">Artists</option><option value="track">Tracks</option><option value="album">Albums</option></select><button className="button-primary" type="submit" disabled={loading || !query.trim()}>{loading ? 'Searching…' : 'Search'}</button></form></section>
    {error ? <p className="rounded-xl border border-rose-400/20 bg-rose-400/5 p-3 text-sm text-rose-200">{error}</p> : null}{notice ? <p className="rounded-xl border border-spotify/20 bg-spotify/5 p-3 text-sm text-spotify-light">{notice}</p> : null}
    {loading ? <div className="panel p-8 text-sm text-muted">Searching your catalog and MusicBrainz…</div> : null}
    {!loading && items.length ? <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{items.map(item => <article key={item.entity_id} className="recommendation-card"><div className="recommendation-art">{item.entity_type === 'artist' ? '♬' : item.entity_type === 'album' ? '▧' : '♫'}</div><div className="p-4"><div className="flex flex-wrap items-center gap-2"><span className="status-pill">{item.entity_type}</span><span className="status-pill">{item.already_cataloged ? 'In your catalog' : 'MusicBrainz result'}</span></div><h3 className="mt-3 text-lg font-semibold text-white">{item.name}</h3>{item.artist_names?.length ? <p className="mt-1 text-sm text-muted">{item.artist_names.join(', ')}</p> : null}{item.release_names?.length ? <p className="mt-1 text-xs text-muted">Release: {item.release_names.slice(0, 2).join(', ')}</p> : null}{item.disambiguation ? <p className="mt-1 text-xs text-muted">{item.disambiguation}</p> : null}{formatDuration(item.length_ms) ? <p className="mt-1 text-xs text-muted">Duration: {formatDuration(item.length_ms)}</p> : null}<div className="mt-4 flex flex-wrap gap-2"><a className="button-secondary inline-flex" href={item.spotify_url} target="_blank" rel="noreferrer">{item.spotify_url_label || (item.spotify_url_type === 'track' ? 'Play on Spotify' : 'Search on Spotify')} ↗</a><button className={selectedEntityId === item.entity_id ? 'button-primary' : 'button-secondary'} onClick={() => setSelectedEntityId(previous => previous === item.entity_id ? '' : item.entity_id)}>{selectedEntityId === item.entity_id ? 'Selected' : 'Select entity'}</button></div>{selectedEntityId === item.entity_id ? <EntityActions item={item} busy={busyId.startsWith(`${item.entity_id}:`)} onAction={updateAction} /> : null}</div></article>)}</div> : null}
    {!loading && searched && !items.length ? <section className="panel p-8"><h3 className="text-lg font-semibold text-white">No matching entities found</h3><p className="mt-2 text-sm text-muted">Try another title, artist name, or entity type.</p></section> : null}
    {!query.trim() ? <section className="panel p-8"><h3 className="text-lg font-semibold text-white">Find music to organize</h3><p className="mt-2 text-sm text-muted">Search for an artist or track to follow, save, or add to your preferred list.</p></section> : null}
  </div>
}
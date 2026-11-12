import { useState } from 'react'
import { apiFetch } from '../api/client'

const entityTypes = [
  { value: 'album', label: 'Albums' },
  { value: 'artist', label: 'Artists' },
  { value: 'track', label: 'Tracks' },
]

function MusicCatalogActions({ memoryConsent }) {
  const [query, setQuery] = useState('')
  const [entityType, setEntityType] = useState('album')
  const [results, setResults] = useState([])
  const [selectedId, setSelectedId] = useState('')
  const [searching, setSearching] = useState(false)
  const [busyAction, setBusyAction] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const searchCatalog = async (event) => {
    event.preventDefault()
    if (!query.trim()) return
    setSearching(true); setError(''); setNotice(''); setSelectedId('')
    try {
      const params = new URLSearchParams({ query: query.trim(), entity_type: entityType, limit: '30' })
      const result = await apiFetch(`/v1/catalog/search?${params.toString()}`)
      setResults(result.results || [])
      if (!(result.results || []).length) setNotice('No catalog matches found. Try another search.')
    } catch (err) {
      setError(err.message)
      setResults([])
    } finally {
      setSearching(false)
    }
  }

  const updateAction = async (item, action) => {
    const active = !Boolean(action === 'save' ? item.is_saved : action === 'follow' ? item.is_followed : item.is_preferred)
    const key = `${item.entity_id}:${action}`
    setBusyAction(key); setError(''); setNotice('')
    try {
      const result = await apiFetch('/v1/catalog/actions', {
        method: 'POST',
        body: JSON.stringify({
          entity_id: item.entity_id,
          entity_type: item.entity_type,
          action,
          active,
          mbid: item.mbid || null,
          name: item.name,
          artist_name: (item.artist_names || []).join(', ') || null,
        }),
      })
      setResults((previous) => previous.map((candidate) => candidate.entity_id === item.entity_id
        ? { ...candidate, is_saved: Boolean(result.actions?.save), is_preferred: Boolean(result.actions?.preference), is_followed: Boolean(result.actions?.follow) }
        : candidate))
      setNotice(`${item.name}: ${action === 'save' ? (active ? 'saved' : 'removed from saved items') : (active ? 'added as a preference' : 'removed from preferences')}.`)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusyAction('')
    }
  }

  const selectedItem = results.find((item) => getItemId(item) === selectedId)

  return <section className="panel p-5 sm:p-6">
    <p className="eyebrow">MUSIC CATALOG</p>
    <h2 className="mt-1 text-xl font-semibold text-white">Find an album, save it, or add it as a preference</h2>
    <p className="mt-2 text-sm text-muted">Search the catalog, select a result, then choose the action. Your choice is saved through the catalog action API.</p>
    <form onSubmit={searchCatalog} className="mt-5 grid gap-3 sm:grid-cols-[170px_1fr_auto]">
      <div>
        <label className="field-label" htmlFor="catalog-entity-type">Search type</label>
        <select id="catalog-entity-type" className="field mt-2 w-full" value={entityType} onChange={(event) => { setEntityType(event.target.value); setResults([]); setSelectedId('') }}>
          {entityTypes.map((type) => <option key={type.value} value={type.value}>{type.label}</option>)}
        </select>
      </div>
      <div>
        <label className="field-label" htmlFor="catalog-query">Search music</label>
        <input id="catalog-query" className="field mt-2 w-full" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={entityType === 'album' ? 'Album title' : entityType === 'artist' ? 'Artist name' : 'Track title'} maxLength={300} />
      </div>
      <div className="flex items-end">
        <button type="submit" className="button-primary w-full sm:w-auto" disabled={searching || !query.trim()}>{searching ? 'Searching…' : 'Search'}</button>
      </div>
    </form>
    {!memoryConsent ? <p className="mt-4 rounded-xl border border-amber-300/20 bg-amber-300/5 p-3 text-sm text-amber-100">Opt in to memory from the account controls before saving albums or adding preferences.</p> : null}
    {error ? <p className="mt-4 rounded-xl border border-rose-400/20 bg-rose-400/5 p-3 text-sm text-rose-200">{error}</p> : null}
    {notice ? <p className="mt-4 rounded-xl border border-spotify/20 bg-spotify/5 p-3 text-sm text-spotify-light">{notice}</p> : null}
    {results.length ? <div className="mt-5 space-y-3">
      {results.map((item) => <article key={getItemId(item)} className="content-row">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2"><span className="status-pill">{item.entity_type}</span>{item.is_saved ? <span className="status-pill status-positive">Saved</span> : null}{item.is_preferred ? <span className="status-pill status-positive">Preferred</span> : null}</div>
          <p className="mt-2 font-semibold text-white">{item.name}</p>
          {(item.artist_names || []).length ? <p className="mt-1 text-sm text-muted">{item.artist_names.join(', ')}</p> : null}
          {item.disambiguation ? <p className="mt-1 text-xs text-muted">{item.disambiguation}</p> : null}
          {item.spotify_url ? <a href={item.spotify_url} target="_blank" rel="noreferrer" className="mt-2 inline-block text-xs text-spotify underline">Open in Spotify ↗</a> : null}
        </div>
        <div className="flex shrink-0 items-start">
          <button type="button" className="button-secondary" aria-expanded={selectedId === getItemId(item)} onClick={() => { const itemId = getItemId(item); setSelectedId((previous) => previous === itemId ? '' : itemId) }}>{selectedId === getItemId(item) ? 'Close' : 'Select'}</button>
        </div>
      </article>)}
    </div> : null}
    {selectedItem ? <div className="mt-4 rounded-xl border border-spotify/20 bg-spotify/5 p-4">
      <p className="text-sm font-semibold text-white">Choose an action for {selectedItem.name}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {selectedItem.entity_type === 'artist' ? <button type="button" className={selectedItem.is_followed ? 'button-secondary' : 'button-primary'} disabled={Boolean(busyAction) || !memoryConsent} onClick={() => updateAction(selectedItem, 'follow')}>{busyAction === `${selectedItem.entity_id}:follow` ? 'Updating…' : selectedItem.is_followed ? 'Unfollow artist' : 'Follow artist'}</button> : null}
        {selectedItem.entity_type !== 'artist' ? <button type="button" className={selectedItem.is_saved ? 'button-secondary' : 'button-primary'} disabled={Boolean(busyAction) || !memoryConsent} onClick={() => updateAction(selectedItem, 'save')}>{busyAction === `${selectedItem.entity_id}:save` ? 'Updating…' : selectedItem.is_saved ? 'Remove saved item' : selectedItem.entity_type === 'album' ? 'Save album' : 'Save track'}</button> : null}
        <button type="button" className={selectedItem.is_preferred ? 'button-secondary' : 'button-primary'} disabled={Boolean(busyAction) || !memoryConsent} onClick={() => updateAction(selectedItem, 'preference')}>{busyAction === `${selectedItem.entity_id}:preference` ? 'Updating…' : selectedItem.is_preferred ? 'Remove preference' : 'Add as Preference'}</button>
      </div>
    </div> : null}
  </section>
}
export default MusicCatalogActions

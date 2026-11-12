import { useCallback, useEffect, useState } from 'react'
import { apiFetch } from '../api/client'

function EntityActionButtons({ item, busy, onAction }) {
  const activeButton = (active, label, removeLabel, action) => active
    ? <div className="flex flex-wrap items-center gap-2"><span className="status-pill status-positive">{label}</span><button className="button-small-danger" disabled={busy} onClick={() => onAction(item, action, false)}>{removeLabel}</button></div>
    : <button className="button-small" disabled={busy} onClick={() => onAction(item, action, true)}>{{follow:'Follow',save:'Save track',preference:'Add as preference'}[action]}</button>
  return <div className="mt-3 flex flex-wrap gap-2">
    {item.entity_type === 'artist' ? activeButton(item.actions?.follow, 'Following', 'Unfollow', 'follow') : null}
    {['track', 'album'].includes(item.entity_type) ? activeButton(item.actions?.save, 'Saved', item.entity_type === 'album' ? 'Remove from saved albums' : 'Remove from saved tracks', 'save') : null}
    {['artist','track','album'].includes(item.entity_type) ? activeButton(item.actions?.preference, 'Added to preferred list', 'Remove from preferred list', 'preference') : null}
  </div>
}
function Folder({ title, description, items, emptyText, busyId, onAction }) {
  return <section className="panel p-4 sm:p-5"><div className="section-heading"><div><h3 className="text-lg font-semibold text-white">{title}</h3><p className="mt-1 text-sm text-muted">{description}</p></div><span className="status-pill">{items.length}</span></div>
    {items.length ? <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">{items.map(item => <article key={item.entity_id} className="content-row"><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><span className="status-pill">{item.entity_type}</span>{item.is_preferred ? <span className="status-pill status-positive">Preferred</span> : null}</div><h4 className="mt-2 font-semibold text-white">{item.name}</h4>{item.artist_names?.length ? <p className="mt-1 text-xs text-muted">{item.artist_names.join(', ')}</p> : null}<a href={item.spotify_url} target="_blank" rel="noreferrer" className="mt-3 inline-flex text-xs font-semibold text-spotify-light hover:underline">{item.spotify_url_label || 'Open on Spotify'} ↗</a><EntityActionButtons item={item} busy={busyId.startsWith(`${item.entity_id}:`)} onAction={onAction} /></div></article>)}</div> : <p className="mt-4 rounded-xl border border-white/10 bg-black/15 p-4 text-sm text-muted">{emptyText}</p>}
  </section>
}
export default function RecommendationsPage() {
  const [folders, setFolders] = useState({saved_tracks:[],saved_albums:[],followed_artists:[],preferred_entities:[]})
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [reason, setReason] = useState('')
  const [busyId, setBusyId] = useState('')
  const load = useCallback(async () => { setLoading(true); setError(''); try { const result = await apiFetch('/v1/recommendations'); setFolders(result.folders || {saved_tracks:[],saved_albums:[],followed_artists:[],preferred_entities:[]}); setReason(result.reason || '') } catch (err) { setError(err.message) } finally { setLoading(false) } }, [])
  useEffect(() => { Promise.resolve().then(load) }, [load])
  const updateAction = async (item, action, active) => {
    const subjectId = (() => { try { return JSON.parse(localStorage.getItem('spotify_ai_session') || 'null')?.subject_id || '' } catch { return '' } })()
    if (localStorage.getItem(`spotify_ai_memory_consent_${subjectId}`) !== 'true') { setError('Enable memory consent in the account controls before changing music lists.'); return }
    const key = `${item.entity_id}:${action}`; setBusyId(key); setError(''); setNotice('')
    try {
      await apiFetch('/v1/catalog/actions', { method: 'POST', body: JSON.stringify({ entity_id:item.entity_id, entity_type:item.entity_type, action, active, name:item.name, artist_name:item.artist_names?.join(', ') || null }) })
      setNotice(`${item.name}: ${active ? ({follow:'followed',save:'saved',preference:'added to your preferred list'}[action]) : ({follow:'unfollowed',save:item.entity_type === 'album' ? 'removed from saved albums' : 'removed from saved tracks',preference:'removed from your preferred list'}[action])}.`)
      await load()
    } catch (err) { setError(err.message) } finally { setBusyId('') }
  }
  const savedTracksAndAlbums = [...(folders.saved_tracks || []), ...(folders.saved_albums || [])].filter((item, index, all) => all.findIndex((candidate) => candidate.entity_id === item.entity_id) === index)
  return <div className="space-y-5"><section className="hero-panel"><div><p className="eyebrow">YOUR MUSIC COLLECTION</p><h2 className="mt-2 text-2xl font-bold text-white sm:text-3xl">Saved, followed, and preferred</h2><p className="mt-3 max-w-2xl text-sm leading-6 text-muted">These folders reflect your current list states. You can change follow, save, and preference status here or from Search Music.</p></div><button type="button" onClick={load} className="button-secondary" disabled={loading}>↻ Refresh</button></section>
    {error ? <p className="rounded-xl border border-rose-400/20 bg-rose-400/5 p-3 text-sm text-rose-200">{error}</p> : null}{notice ? <p className="rounded-xl border border-spotify/20 bg-spotify/5 p-3 text-sm text-spotify-light">{notice}</p> : null}
    {loading ? <div className="panel p-8 text-sm text-muted">Loading your music folders…</div> : <>{reason ? <p className="rounded-xl border border-white/10 bg-black/15 p-3 text-sm text-muted">{reason}</p> : null}<Folder title="Saved tracks and albums" description="Tracks and albums you've saved for later." items={savedTracksAndAlbums} emptyText="No saved tracks or albums yet. Search the catalog and save a track or album to see it here." busyId={busyId} onAction={updateAction} /><Folder title="Followed artists" description="Artists you currently follow." items={folders.followed_artists || []} emptyText="No followed artists yet. Follow an artist from Search Music to add them here." busyId={busyId} onAction={updateAction} /><Folder title="Preferred artists, tracks and albums" description="Entities you've explicitly added to your preferred list." items={folders.preferred_entities || []} emptyText="No preferred artists or tracks or albums yet. Add a preference from Search Music or Chat." busyId={busyId} onAction={updateAction} /></>}
  </div>
}

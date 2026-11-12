import { Link } from 'react-router-dom'

/**
 * Memory search panel.
 *
 * Queries the backend for candidate memories relevant to a user intent.
 */

function MemorySearchPanel({ searchIntent, setSearchIntent, searchResult, searchLoading, onSubmit, session, memoryActionLoading, memoryActionError, onEdit, onDelete }) {
  const editPreference = async (candidate) => {
    const currentText = candidate.normalized_fact || candidate.memory_text || candidate.content || ''
    const updatedText = window.prompt(`Edit preference for memory ${candidate.memory_id}:`, currentText)
    if (updatedText?.trim()) await onEdit(candidate.memory_id, updatedText)
  }

  return (
    <div className="rounded-2xl border border-slate-700/80 bg-slate-900/70 p-5 shadow-xl shadow-slate-950/30">
      <div className="mb-4 flex items-center justify-between">
        <p className="text-xs uppercase tracking-[0.18em] text-emerald-400">Memory Search</p>
        <span className="rounded-full border border-emerald-400/30 bg-emerald-500/10 px-2 py-1 text-xs text-emerald-200">/v1/memories/search</span>
      </div>

      <form onSubmit={onSubmit} className="space-y-3">
        <input
          value={searchIntent}
          onChange={(e) => setSearchIntent(e.target.value)}
          className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none transition focus:border-emerald-500"
          placeholder="Search intent"
        />
        <button
          type="submit"
          disabled={searchLoading || !session}
          className="rounded-xl bg-emerald-500 px-4 py-2.5 font-semibold text-slate-950 transition hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {searchLoading ? 'Searching…' : 'Search memories'}
        </button>
      </form>

      {searchResult ? (
        <div className="mt-4 overflow-hidden rounded-xl border border-slate-700 bg-slate-950/80 p-4">
          {searchResult.error ? (
            <p className="text-rose-400">{searchResult.error}</p>
          ) : (
            <>
              <p className="mb-3 text-sm text-slate-300">Decision: {searchResult.decision}</p>
              <div className="space-y-3 text-sm">
                {searchResult.candidates?.length ? (
                  searchResult.candidates.map((candidate, index) => (
                    <div key={`${candidate.memory_id || 'candidate'}-${index}`} className="rounded-xl border border-slate-700 bg-slate-900/80 p-3">
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <p className="font-medium text-emerald-300">#{index + 1} · {candidate.memory_id || 'memory'}</p>
                        {candidate.memory_id ? (
                          <div className="flex gap-2">
                            <button
                              type="button"
                              onClick={() => editPreference(candidate)}
                              disabled={Boolean(memoryActionLoading)}
                              className="rounded-lg border border-sky-400/40 px-3 py-1 text-xs font-semibold text-sky-200 transition hover:border-sky-300 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                            >
                              Edit
                            </button>
                            <button
                              type="button"
                              onClick={() => onDelete(candidate.memory_id)}
                              disabled={Boolean(memoryActionLoading)}
                              className="rounded-lg border border-rose-400/40 px-3 py-1 text-xs font-semibold text-rose-300 transition hover:border-rose-300 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
                            >
                              Delete preference
                            </button>
                          </div>
                        ) : null}
                      </div>
                      <p className="mt-2 text-slate-200">{candidate.normalized_fact || candidate.memory_text || candidate.content || JSON.stringify(candidate)}</p>
                    </div>
                  ))
                ) : (
                  <p className="text-slate-400">No matches found.</p>
                )}
              </div>
              {memoryActionError ? (
                <p className="mt-3 text-sm text-rose-400">
                  {memoryActionError}
                  {memoryActionError.includes('requires consent') ? (
                    <Link to="/events" className="ml-1 text-sky-300 underline hover:text-sky-200">
                      Open consent settings
                    </Link>
                  ) : null}
                </p>
              ) : null}
            </>
          )}
        </div>
      ) : null}
    </div>
  )
}

export default MemorySearchPanel

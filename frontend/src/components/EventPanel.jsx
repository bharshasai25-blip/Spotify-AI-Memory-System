/**
 * Event ingestion panel.
 *
 * Lets a user submit an event to the backend and inspect the ingestion result payload.
 */

function EventPanel({ eventForm, setEventForm, eventResult, eventLoading, onSubmit, session, memoryConsent, consentLoading, consentError, onConsentChange }) {
  return (
    <div className="rounded-2xl border border-slate-700/80 bg-slate-900/70 p-5 shadow-xl shadow-slate-950/30">
      <div className="mb-4 flex items-center justify-between">
        <p className="text-xs uppercase tracking-[0.18em] text-amber-400">Event Ingestion</p>
        <span className="rounded-full border border-amber-400/30 bg-amber-500/10 px-2 py-1 text-xs text-amber-200">/v1/events</span>
      </div>

      <div className="mb-5 rounded-xl border border-sky-400/30 bg-sky-500/10 p-4">
        <label className="flex cursor-pointer items-start gap-3">
          <input
            type="checkbox"
            checked={memoryConsent}
            onChange={(e) => onConsentChange(e.target.checked)}
            disabled={consentLoading || !session}
            className="mt-1 h-4 w-4 accent-sky-400"
          />
          <span>
            <span className="block font-semibold text-sky-100">Allow memory saving</span>
            <span className="mt-1 block text-sm text-slate-300">
              Permit this app to save submitted preferences and interactions as memories.
            </span>
          </span>
        </label>
        <p className="mt-3 text-xs text-slate-400">
          {consentLoading ? "Updating your consent…" : memoryConsent ? "Memory saving is enabled." : "Memory saving is disabled until you opt in."}
        </p>
        {consentError ? <p className="mt-2 text-sm text-rose-400">{consentError}</p> : null}
      </div>

      <form onSubmit={onSubmit} className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <select
            value={eventForm.event_type}
            onChange={(e) => setEventForm({ ...eventForm, event_type: e.target.value })}
            className="rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none transition focus:border-amber-500"
          >
            {['ai_interaction', 'playback', 'save', 'follow', 'skip', 'explicit_preference'].map((option) => (
              <option key={option} value={option}>{option}</option>
            ))}
          </select>

          <input
            value={eventForm.surface}
            onChange={(e) => setEventForm({ ...eventForm, surface: e.target.value })}
            className="rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none transition focus:border-amber-500"
            placeholder="surface"
          />
        </div>

        {eventForm.event_type === 'playback' ? (
          <select
            value={eventForm.playback_action}
            onChange={(e) => setEventForm({ ...eventForm, playback_action: e.target.value })}
            className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none transition focus:border-amber-500"
          >
            <option value="play">play</option>
            <option value="pause">pause</option>
          </select>
        ) : null}

        <input
          value={eventForm.locale}
          onChange={(e) => setEventForm({ ...eventForm, locale: e.target.value })}
          className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none transition focus:border-amber-500"
          placeholder="locale"
        />

        <textarea
          value={eventForm.text}
          onChange={(e) => setEventForm({ ...eventForm, text: e.target.value })}
          rows={3}
          className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-slate-100 outline-none transition focus:border-amber-500"
          placeholder="Text payload"
        />

        <textarea
          value={eventForm.metadata}
          onChange={(e) => setEventForm({ ...eventForm, metadata: e.target.value })}
          rows={2}
          className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-xs text-slate-100 outline-none transition focus:border-amber-500"
          placeholder='{"playback_action":"play"}'
        />

        <button
          type="submit"
          disabled={eventLoading || !session || !memoryConsent || consentLoading}
          className="rounded-xl bg-amber-500 px-4 py-2.5 font-semibold text-slate-950 transition hover:bg-amber-400 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {eventLoading ? 'Submitting…' : 'Submit event'}
        </button>
      </form>

      {eventResult ? (
        <div className="mt-4 overflow-hidden rounded-xl border border-slate-700 bg-slate-950/80 p-4">
          {eventResult.error ? (
            <p className="text-rose-400">{eventResult.error}</p>
          ) : (
            <pre className="text-xs text-slate-200">{JSON.stringify(eventResult, null, 2)}</pre>
          )}
        </div>
      ) : null}
    </div>
  )
}

export default EventPanel

import { useState, useEffect, useRef } from 'react'

const API = 'http://localhost:8000'
const DESTINATIONS = ['dock', 'kitchen', 'room_a', 'room_b']

const STATE_COLOR = {
  IDLE: 'text-zinc-400',
  QUEUED: 'text-amber-400',
  NAVIGATING: 'text-cyan-400',
  DELIVERING: 'text-cyan-400',
  RETURNING: 'text-amber-400',
  DOCKING: 'text-amber-400',
  DOCKED: 'text-emerald-400',
}

function genOrderId() {
  return 'ORD-' + Math.floor(1000 + Math.random() * 9000)
}

export default function App() {
  const [status, setStatus] = useState(null)
  const [connected, setConnected] = useState(false)
  const [destination, setDestination] = useState(DESTINATIONS[0])
  const [log, setLog] = useState([])
  const lastState = useRef(null)

  useEffect(() => {
    const poll = async () => {
      try {
        const res = await fetch(`${API}/robot/status`)
        const data = await res.json()
        setStatus(data)
        setConnected(true)
        if (data.state !== lastState.current) {
          setLog((prev) => [
            { state: data.state, at: new Date().toLocaleTimeString() },
            ...prev,
          ].slice(0, 8))
          lastState.current = data.state
        }
      } catch {
        setConnected(false)
      }
    }
    poll()
    const id = setInterval(poll, 1500)
    return () => clearInterval(id)
  }, [])

  const submit = async (e) => {
    e.preventDefault()
    await fetch(`${API}/delivery`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ order_id: genOrderId(), destination }),
    })
  }

  const battery = status?.battery ?? 0
  const state = status?.state ?? 'UNKNOWN'

  return (
    <div className="min-h-screen bg-[#0a0e14] text-zinc-200 font-sans">
      <div className="max-w-3xl mx-auto px-6 py-10">

        <header className="flex items-center justify-between border-b border-zinc-800 pb-4 mb-8">
          <h1 className="text-lg font-medium tracking-tight text-zinc-100">
            TuniBot Dispatch
          </h1>
          <div className="flex items-center gap-2 text-sm text-zinc-500">
            <span className={`h-2 w-2 rounded-full ${connected ? 'bg-emerald-400' : 'bg-red-500'}`} />
            {connected ? 'Connected' : 'Offline'}
          </div>
        </header>

        <section className="border border-zinc-800 rounded-md p-6 mb-6">
          <div className="flex items-baseline justify-between mb-6">
            <span className="text-xs uppercase tracking-wide text-zinc-500">Robot state</span>
            <span className="font-mono text-xs text-zinc-600">
              {status?.current_order ? status.current_order : 'no active order'}
            </span>
          </div>
          <div className={`text-4xl font-mono font-medium mb-6 ${STATE_COLOR[state] ?? 'text-zinc-400'}`}>
            {state}
          </div>
          <div>
            <div className="flex justify-between text-xs text-zinc-500 mb-1">
              <span>Battery</span>
              <span className="font-mono">{battery.toFixed(0)}%</span>
            </div>
            <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${battery < 30 ? 'bg-red-500' : 'bg-emerald-400'}`}
                style={{ width: `${battery}%` }}
              />
            </div>
          </div>
        </section>

        <section className="border border-zinc-800 rounded-md p-6 mb-6">
          <span className="text-xs uppercase tracking-wide text-zinc-500 block mb-4">
            New delivery
          </span>
          <form onSubmit={submit} className="flex gap-3">
            <select
              value={destination}
              onChange={(e) => setDestination(e.target.value)}
              className="flex-1 bg-zinc-900 border border-zinc-700 rounded px-3 py-2 text-sm font-mono focus:outline-none focus:border-cyan-500"
            >
              {DESTINATIONS.map((d) => (
                <option key={d} value={d}>{d}</option>
              ))}
            </select>
            <button
              type="submit"
              className="px-5 py-2 bg-cyan-600 hover:bg-cyan-500 text-white text-sm rounded transition-colors"
            >
              Send delivery
            </button>
          </form>
        </section>

        <section className="border border-zinc-800 rounded-md p-6">
          <span className="text-xs uppercase tracking-wide text-zinc-500 block mb-4">
            Activity
          </span>
          <ul className="space-y-2">
            {log.length === 0 && (
              <li className="text-sm text-zinc-600">No state changes yet.</li>
            )}
            {log.map((entry, i) => (
              <li key={i} className="flex justify-between text-sm font-mono">
                <span className={STATE_COLOR[entry.state] ?? 'text-zinc-400'}>{entry.state}</span>
                <span className="text-zinc-600">{entry.at}</span>
              </li>
            ))}
          </ul>
        </section>

      </div>
    </div>
  )
}

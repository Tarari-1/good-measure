import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../api'

export interface Loaded<T> {
  data: T | null
  error: string | null
  loading: boolean
  reload: () => void
}

/** Load once (and again when `deps` or `reload()` change). Optional polling interval in ms. */
export function useLoad<T>(fn: () => Promise<T>, deps: unknown[] = [], intervalMs?: number): Loaded<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [tick, setTick] = useState(0)
  const fnRef = useRef(fn)
  fnRef.current = fn

  useEffect(() => {
    let alive = true
    const run = () =>
      fnRef
        .current()
        .then((d) => {
          if (!alive) return
          setData(d)
          setError(null)
        })
        .catch((e: unknown) => {
          if (alive) setError(e instanceof ApiError || e instanceof Error ? e.message : 'Something went wrong.')
        })
        .finally(() => alive && setLoading(false))
    void run()
    const id = intervalMs ? window.setInterval(run, intervalMs) : undefined
    return () => {
      alive = false
      if (id) window.clearInterval(id)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tick, intervalMs, ...deps])

  const reload = useCallback(() => setTick((t) => t + 1), [])
  return { data, error, loading, reload }
}

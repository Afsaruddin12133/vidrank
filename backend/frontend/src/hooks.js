import { useCallback, useEffect, useRef, useState } from 'react'

// Lightweight live polling: runs fn immediately, then every `ms`.
// Interval cleaned up on unmount. Errors never crash — callers render
// their own empty/error states.
export function usePoll(fn, ms = 5000, deps = []) {
  const fnRef = useRef(fn)
  fnRef.current = fn
  const [tick, setTick] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), ms)
    return () => clearInterval(id)
  }, [ms, ...deps])
  useEffect(() => {
    fnRef.current()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tick])
}

// Async-loader wrapper: { data, error } refreshed on every poll tick.
export function usePolled(loader, ms = 5000, deps = []) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const cb = useCallback(async () => {
    try {
      setData(await loader())
      setError(null)
    } catch (e) {
      setError(e)
    }
  }, [loader, ...deps])
  usePoll(cb, ms, deps)
  return { data, error }
}

export function useNow(ms = 1000) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), ms)
    return () => clearInterval(id)
  }, [ms])
  return now
}

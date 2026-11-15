import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../lib/api";
import type { Job } from "../lib/types";

export interface Async<T> { data: T | null; error: string | null; loading: boolean; reload: () => void }

/** Run an async loader whenever `deps` change. A `null` loader means "nothing to load". */
export function useAsync<T>(loader: (() => Promise<T>) | null, deps: unknown[]): Async<T> {
  const [state, setState] = useState<{ data: T | null; error: string | null; loading: boolean }>(
    { data: null, error: null, loading: loader !== null });
  const [tick, setTick] = useState(0);
  const ref = useRef(loader);
  ref.current = loader;
  useEffect(() => {
    const fn = ref.current;
    if (fn === null) {
      setState({ data: null, error: null, loading: false });
      return;
    }
    let live = true;
    setState((s) => ({ ...s, loading: true, error: null }));
    fn().then(
      (data) => { if (live) setState({ data, error: null, loading: false }); },
      (e: unknown) => { if (live) setState({ data: null, error: e instanceof Error ? e.message : String(e), loading: false }); },
    );
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { ...state, reload };
}

/** Poll a background job until it finishes; `onDone` fires once per job. */
export function useJob(jobId: string | null, onDone?: (job: Job) => void): Job | null {
  const [job, setJob] = useState<Job | null>(null);
  const cb = useRef(onDone);
  cb.current = onDone;
  useEffect(() => {
    if (!jobId) { setJob(null); return; }
    let live = true;
    let timer = 0;
    const poll = () => {
      api.job(jobId).then((j) => {
        if (!live) return;
        setJob(j);
        if (j.status === "queued" || j.status === "running") timer = window.setTimeout(poll, 500);
        else cb.current?.(j);
      }, () => { if (live) timer = window.setTimeout(poll, 1500); });
    };
    poll();
    return () => { live = false; window.clearTimeout(timer); };
  }, [jobId]);
  return job;
}

export const isActive = (j: Job | null | undefined) => !!j && (j.status === "queued" || j.status === "running");

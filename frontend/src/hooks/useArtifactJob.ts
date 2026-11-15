import { useCallback, useState } from "react";
import { adv, type AnyJson } from "../lib/api";
import type { Job } from "../lib/types";
import { useApp } from "../stores/app";
import { isActive, useJob } from "./useAsync";

/** Start a backend job whose result is an artifact id, then load one part of that artifact. */
export function useArtifactJob<R = AnyJson>(part: string, onLoaded?: (r: R, id: string) => void) {
  const notify = useApp((s) => s.notify);
  const [jobId, setJobId] = useState<string | null>(null);
  const [result, setResult] = useState<R | null>(null);
  const [artifactId, setArtifactId] = useState<string | null>(null);
  const job = useJob(jobId, (j: Job) => {
    if (j.status !== "completed") {
      notify("error", j.error ?? `job ${j.status}`);
      return;
    }
    const id = String((j as unknown as { result: unknown }).result);
    adv.artifact<R>(id, part).then((r) => { setResult(r); setArtifactId(id); onLoaded?.(r, id); },
      (e: Error) => notify("error", e.message));
  });
  const start = useCallback(async (launch: () => Promise<Job>) => {
    try {
      const j = await launch();
      setJobId(j.id);
    } catch (e) {
      notify("error", (e as Error).message);
    }
  }, [notify]);
  const load = useCallback((id: string) => {
    adv.artifact<R>(id, part).then((r) => { setResult(r); setArtifactId(id); },
      (e: Error) => notify("error", e.message));
  }, [part, notify]);
  return { start, job, busy: isActive(job), result, artifactId, load, setResult };
}

import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { Dict, ExperimentDetail, ModelDetail, Pose } from "../lib/types";
import { useApp } from "../stores/app";
import { useAsync, type Async } from "./useAsync";

export function useModel(): Async<ModelDetail> {
  const modelId = useApp((s) => s.modelId);
  return useAsync(modelId ? () => api.model(modelId) : null, [modelId]);
}

export function useExperiment(): Async<ExperimentDetail> {
  const id = useApp((s) => s.experimentId);
  return useAsync(id ? () => api.experiment(id) : null, [id]);
}

/** Backend kinematics for a joint configuration (debounced while sliders move). */
export function usePose(modelId: string | null, pose: Dict, values?: Dict | null): Pose | null {
  const [result, setResult] = useState<Pose | null>(null);
  const key = JSON.stringify([pose, values ?? null]);
  useEffect(() => {
    if (!modelId) { setResult(null); return; }
    let live = true;
    const timer = window.setTimeout(() => {
      api.pose(modelId, pose, values).then((p) => { if (live) setResult(p); }, () => { if (live) setResult(null); });
    }, 40);
    return () => { live = false; window.clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modelId, key]);
  return result;
}

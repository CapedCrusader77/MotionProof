# Root-cause analysis

`motionproof/rootcause/analysis.py`. For one failed scenario:

1. Re-simulate it and pick the violated metric.
2. **Association**: Kolmogorov-Smirnov comparison of each variable between failing and passing
   scenarios of the experiment. Association only.
3. **Local sensitivity**: central differences at the failing point (5 % of each range); the
   first-order share of the excess is slope x (value - nominal).
4. **Counterfactual reruns**: the scenario re-simulated with each leading variable alone at its
   nominal value. This is the causal evidence within the model.
5. A written explanation assembled only from those numbers.

The failure-investigation screen shows the explanation, the ranking (value, reference, local
effect, rerun result, whether it fixes the failure, association p-value) and the replayed
traces. The optional AI assistant may paraphrase the evidence; it does not decide causes.

Verified (benchmark N): a deliberately dominant backlash variable is ranked first and its rerun
removes the failure.

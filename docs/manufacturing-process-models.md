# Manufacturing process models

`motionproof/process/model.py`. A statistical, explicitly parameterised process model, not a
machining simulation.

    x = target + drift(part index in tool life) + batch + setup + tool + part + measurement

* Every source has a standard deviation, a basis (`measured`, `specified`, `assumed`) and an
  on/off switch. None is defaulted.
* A source with a `shared_group` is drawn once per batch, setup or tool and added to every
  feature in that group: two bores bored in one fixture move together. Correlation is never
  assumed from belonging to one component.
* Drift: linear, piecewise or measured breakpoints; optional random walk; reset at each tool
  change.
* Measurement noise affects the measured values only, not the parts.

Analyses: per-feature mean, standard deviation, overall Cp/Cpk and out-of-spec share;
variance components by balanced nested ANOVA (method of moments; few batches are flagged as
imprecise); X-bar control chart with beyond-limit, nine-point run and trend signals (absence of
a signal is not a stability claim); linear drift fit; feature correlation; and the fits of every
virtual assembly built from the batch.

Validated on SYNTHETIC batches (benchmark G): components recovered within 3-12 %, the shared
setup error cancels in a clearance exactly as `var = 2 (s_batch^2 + s_part^2)` predicts.

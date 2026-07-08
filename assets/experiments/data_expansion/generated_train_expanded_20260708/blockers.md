# Stage 3D blockers register
1. RESOLVED — weak goals: goal-content precheck; 130/130 pass.
2. OBSERVED — kujiale_0118 rejects ~50% of candidate routes at the
   goal-content gate (featureless floor regions); acceptable at current
   scale, but larger generation targets there will need more candidate
   oversampling (bump the `while len(routes) < N_EP*2` factor).
3. NOTE — the 0118 run yielded exactly 37 strong candidates for a
   37-episode request; headroom was thin. Oversampling factor is the
   knob if a future run asserts short.

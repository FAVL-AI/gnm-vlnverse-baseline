# Stage 3A blockers register

1. RESOLVED — composed-stage relative asset paths (654 broken refs):
   authors' CWD-relative paths; fixed with one `ln -s ../../.. datasets`
   symlink per scene dir; refs 654 → 0; no files modified.
2. OPEN — occupancy/world coordinate convention: occupancy.json
   center/scale vs stage metres mapping unverified; camera placed at the
   raw centre renders floor close-up. Needs calibration against
   rooms.json polygons before A* waypoints can be rendered.
3. OPEN — vistube upstream pipeline remains hardwired to the original
   authors' infrastructure (/mnt/6t, /data/lsh). With local composed
   stages, the practical route is our own generator: A* over
   occupancy.png (as vistube's discrete planner does) + Isaac render
   loop emitting frames + traj_data.pkl in the existing dataset format.
4. MINOR — displayColor primvar size warnings on some floor/window
   meshes (cosmetic; Hydra renders).
5. MINOR — kit swallows plain stdout prints in this harness; scripts
   must write reports to files (this run's PPM/JSON pattern).

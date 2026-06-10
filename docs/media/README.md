# docs/media — Visual assets for the FleetSafe README

Drop screenshots here, then uncomment the corresponding `![…](docs/media/…)` lines
at the top of the root README.

## Needed (high priority)

| Filename | Content | How to capture |
|---|---|---|
| `isaac_hospital_scene.png` | Isaac Sim viewport with hospital USD loaded — show zones, agent capsules, lighting | Isaac Sim GUI → screenshot |
| `dashboard_terminal.png` | Terminal dashboard output — `--watch 5`, ideally with social risk section visible | `python scripts/dashboard/fleetsafe_dashboard.py` → screenshot terminal |
| `dashboard_html.png` | HTML dashboard in browser — show KPI cards + bar chart + zone bars | `python scripts/dashboard/fleetsafe_dashboard.py --html --open` → screenshot browser |
| `yahboom_m3pro.jpg` | Physical Yahboom M3Pro robot — clear shot showing LiDAR + camera | Photo |
| `intervention_overlay.gif` | Animation: raw cmd_vel arrow vs safe cmd_vel arrow during CBF intervention | Render from replay JSON (future: replay viewer) |

## Recommended resolution

- PNG screenshots: 1920×1080 or 2560×1440, saved at 80% quality
- GIF: < 5 MB, 15 fps, 800×450 px
- JPG robot photo: > 1 MP, good lighting

## README image block (currently commented out)

```markdown
![Isaac hospital scene — semantic zones and agent capsules](docs/media/isaac_hospital_scene.png)
![FleetSafe live dashboard](docs/media/dashboard_terminal.png)
![Intervention overlay — raw vs safe cmd_vel](docs/media/intervention_overlay.gif)
![Yahboom RosMaster M3Pro](docs/media/yahboom_m3pro.jpg)
```

Uncomment this block in README.md once the files exist.

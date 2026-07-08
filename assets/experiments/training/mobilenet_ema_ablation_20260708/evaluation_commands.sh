# offline stage-1 evaluation, held-out val split (weights auto: EMA shadow when present)
python scripts/gnm/06_evaluate.py --ckpt checkpoints/ablation_mnv2_baseline/best.pt
python scripts/gnm/06_evaluate.py --ckpt checkpoints/ablation_mnv2_ema/best.pt
python scripts/gnm/06_evaluate.py --ckpt checkpoints/ablation_mnv2_ema0999/best.pt
# stage-2 Isaac physics smoke (isaac env): m3pro_ros2_bringup.py --gnm-control --episode --collision-report --scene hospital --policy-ckpt <ckpt> --goal-id <goal> ... ; table: scripts/gnm/isaac_physics_eval.py

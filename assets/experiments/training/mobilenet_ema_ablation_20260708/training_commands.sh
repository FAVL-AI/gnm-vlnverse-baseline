# executed in gnm_train env, WANDB_MODE=offline, PYTHONPATH=repo root
python scripts/gnm/04_train_gnm.py --cfg configs/gnm/gnm_base.yaml checkpoint.output_dir=checkpoints/ablation_mnv2_baseline wandb.name=mnv2_baseline_for_ema_ablation
python scripts/gnm/04_train_gnm.py --cfg configs/gnm/gnm_base.yaml training.ema_decay=0.9999 checkpoint.output_dir=checkpoints/ablation_mnv2_ema wandb.name=mnv2_ema_ablation
python scripts/gnm/04_train_gnm.py --cfg configs/gnm/gnm_base.yaml training.ema_decay=0.999 checkpoint.output_dir=checkpoints/ablation_mnv2_ema0999 wandb.name=mnv2_ema0999_sanity_ablation

# split materialization (manifest-based symlink tree, gitignored)
python3 scripts/gnm/build_scene_holdout_split.py   # manifest source of truth
# training (gnm_train env, WANDB_MODE=offline, PYTHONPATH=repo)
python scripts/gnm/04_train_gnm.py --cfg configs/gnm/gnm_base.yaml data.data_root=datasets/vlntube_scene_holdout checkpoint.output_dir=checkpoints/scene_holdout_mnv2_baseline wandb.name=mobilenet_baseline_scene_holdout_seed42
python scripts/gnm/04_train_gnm.py --cfg configs/gnm/gnm_base.yaml data.data_root=datasets/vlntube_scene_holdout training.ema_decay=0.999 checkpoint.output_dir=checkpoints/scene_holdout_mnv2_ema0999 wandb.name=mobilenet_ema0999_scene_holdout_seed42
# single test-scene evaluation per checkpoint (kujiale_0271 only, n=50)
python scripts/gnm/06_evaluate.py --ckpt checkpoints/scene_holdout_mnv2_baseline/best.pt --data-root datasets/vlntube_scene_holdout --split test
python scripts/gnm/06_evaluate.py --ckpt checkpoints/scene_holdout_mnv2_ema0999/best.pt --data-root datasets/vlntube_scene_holdout --split test

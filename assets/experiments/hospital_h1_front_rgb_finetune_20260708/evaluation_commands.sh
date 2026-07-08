# diagnostic baseline (top-down incumbent, out-of-domain by design)
python scripts/gnm/06_evaluate.py --ckpt checkpoints/scene_holdout_mnv2_baseline/best.pt --data-root datasets/isaac_hospital_split --split test
# one-shot held-out evaluation of the fine-tuned candidate
python scripts/gnm/06_evaluate.py --ckpt checkpoints/hospital_front_rgb_finetune/best.pt --data-root datasets/isaac_hospital_split --split test

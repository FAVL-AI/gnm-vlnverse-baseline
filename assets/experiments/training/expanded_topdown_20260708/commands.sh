# Stage 4 training (gnm_train env, WANDB_MODE=offline, PYTHONPATH=repo)
python scripts/gnm/04_train_gnm.py --cfg configs/gnm/gnm_base.yaml data.data_root=datasets/vlntube_expanded checkpoint.output_dir=checkpoints/expanded_topdown_mnv2 wandb.name=mobilenet_expanded_topdown_scene_holdout_seed42
# Stage 5 single frozen-scene evaluation (ONE run, after training)
python scripts/gnm/06_evaluate.py --ckpt checkpoints/expanded_topdown_mnv2/best.pt --data-root datasets/vlntube_expanded --split test
# governance
python /home/favl/driftguard/examples/gnm_vlnverse_promotion_gate.py <incumbent_card> <candidate_card> driftguard_decision.json

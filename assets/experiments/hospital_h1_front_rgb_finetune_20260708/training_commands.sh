# batch conversion (system python + humble)
python3 scripts/datasets/convert_hospital_rosbags_to_gnm.py <traj_dir> 12   # x24 episodes
# fine-tune (gnm_train env; init from incumbent weights, fresh optimizer)
python scripts/gnm/04_train_gnm.py --cfg configs/gnm/gnm_base.yaml data.data_root=datasets/isaac_hospital_split training.init_ckpt=checkpoints/scene_holdout_mnv2_baseline/best.pt checkpoint.output_dir=checkpoints/hospital_front_rgb_finetune wandb.name=mobilenet_hospital_front_rgb_finetune_seed42

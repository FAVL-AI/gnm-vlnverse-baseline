# GoStanford2 — Download Instructions

GoStanford2 is part of the drive-any-robot (DARo) dataset release.

## Step 1 — Accept the data-use agreement
Visit: https://sites.google.com/view/drive-any-robot
or:    https://huggingface.co/datasets/robodhruv/drive-any-robot

## Step 2 — Download
After accepting, you will receive a download link or can clone from HuggingFace:

    # Option A — HuggingFace (requires git-lfs)
    git lfs install
    git clone https://huggingface.co/datasets/robodhruv/drive-any-robot

    # Option B — direct tar.gz link (provided after accepting agreement)
    wget <link-from-project-page> -O gostanford2.tar.gz
    tar -xzf gostanford2.tar.gz -C /home/favl/robotics/FleetSafe-VisualNav-Benchmark/data/gnm_datasets/gostanford2/

## Step 3 — Expected layout
    /home/favl/robotics/FleetSafe-VisualNav-Benchmark/data/gnm_datasets/gostanford2/train/traj_0000/0.jpg
    /home/favl/robotics/FleetSafe-VisualNav-Benchmark/data/gnm_datasets/gostanford2/train/traj_0000/traj_data.pkl
    /home/favl/robotics/FleetSafe-VisualNav-Benchmark/data/gnm_datasets/gostanford2/test/traj_0001/0.jpg
    ...

## Step 4 — Validate
    python scripts/data/setup_gnm_indoor_datasets.py --dataset gostanford2

## Citation
Shah, D., Osinski, B., Ichter, B., & Levine, S. (2023). GNM: A General Navigation Model to Drive Any Robot. ICRA 2023. https://arxiv.org/abs/2210.03370

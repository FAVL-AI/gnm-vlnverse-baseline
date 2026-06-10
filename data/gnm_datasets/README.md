        # GNM Indoor Datasets — FleetSafe-VisualNav-Benchmark

        This directory contains (or placeholders for) GNM-compatible training
        datasets relevant to indoor / hospital-corridor navigation.

        ## Dataset Summary

        | Dataset | Hospital Relevance | Environment | Access |
        |---------|-------------------|-------------|--------|
        | GoStanford2 | HIGH | indoor | request |
| SCAND (Social Comfort-Aware Navigation Dataset) | MEDIUM | indoor_and_outdoor | public |
| TartanDrive | LOW | outdoor_offroad | public |
| RECON | NONE | outdoor_exploration | restricted |

        ## Directory Layout

            gnm_datasets/
                gostanford2/          ← GoStanford2 (indoor corridors — BEST MATCH)
                scand/                ← SCAND (indoor+outdoor corridors)
                yahboom_hospital/     ← Real Yahboom M3Pro hospital recordings
                dataset_registry.json ← Machine-readable catalogue
                README.md             ← This file

        ## GNM Trajectory Format

        Each trajectory is a folder with:
            traj_NNNN/
                0.jpg               ← first frame
                1.jpg
                ...
                traj_data.pkl       ← {"position": np.array([[x,y],...], shape [T,2]),
                                        "yaw": np.array([...], shape [T])}

        ## Usage with Fine-Tuning

            # Validate all datasets
            python scripts/data/setup_gnm_indoor_datasets.py

            # Convert FleetSafe episodes → GNM format for fine-tuning
            python scripts/data/gnm_dataset_converter.py fleetsafe-to-gnm \
                --input data/training_episodes/gnm/hospital_corridor \
                --output data/gnm_datasets/fleetsafe_converted/

            # Launch GNM fine-tuning (requires visualnav-transformer)
            cd third_party/visualnav-transformer/train
            python train.py \
                --config ../config/gnm/gnm.yaml \
                --data-dir ../../../data/gnm_datasets/ \
                --pretrained gnm.pth

        ## Why GoStanford2 for Hospitals?

        Hospital corridors share key visual features with office corridors:
        - Long straight hallways with uniform lighting
        - Doorways at regular intervals
        - Hard floors with low visual texture
        - Dynamic obstacles (people, carts) at low density

        GoStanford2 was collected in the Gates CS Building at Stanford University,
        which has very similar visual statistics to a modern hospital wing.

        ## References

        - GNM paper: https://arxiv.org/abs/2210.03370
        - drive-any-robot: https://sites.google.com/view/drive-any-robot
        - SCAND: https://cs.utexas.edu/~xiao/SCAND/SCAND.html

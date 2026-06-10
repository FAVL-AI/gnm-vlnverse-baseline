# Yahboom M3Pro Hospital Recordings

This directory holds GNM-format trajectories recorded with the
Yahboom M3Pro robot (Jetson Orin NX) in a real hospital environment.

## Recording
Use the ROS2 recording pipeline on the robot:

    ros2 bag record /usb_cam/image_raw /odom -o <session_name>

## Converting to GNM format
    python scripts/data/gnm_dataset_converter.py ros2-bag-to-gnm \
        --bag <session_name>/<session_name>.db3 \
        --output data/gnm_datasets/yahboom_hospital/ \
        --camera-topic /usb_cam/image_raw \
        --odom-topic /odom

## Expected layout after conversion
    yahboom_hospital/
        traj_0000/
            0.jpg
            1.jpg
            ...
            traj_data.pkl
        traj_0001/
            ...

## Robot specs (Yahboom M3Pro / Jetson Orin NX)
- Wheel radius : 0.048 m
- Half wheelbase (lx) : 0.0775 m
- Half track width (ly) : 0.0850 m
- Drive type : mecanum

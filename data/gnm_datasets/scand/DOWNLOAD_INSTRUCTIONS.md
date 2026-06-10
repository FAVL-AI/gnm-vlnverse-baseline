# SCAND — Download Instructions

SCAND (Social Comfort-Aware Navigation Dataset) is freely available
from UT Austin.

## Download
Project page: https://cs.utexas.edu/~xiao/SCAND/SCAND.html

Download the **Processed Data** archive (recommended) or the raw ROS bags.

## Extract
    tar -xzf SCAND_processed.tar.gz -C /home/favl/robotics/FleetSafe-VisualNav-Benchmark/data/gnm_datasets/scand/

## Convert to GNM format (for fine-tuning)
    python scripts/data/gnm_dataset_converter.py ros2-bag-to-gnm \
        --bag /home/favl/robotics/FleetSafe-VisualNav-Benchmark/data/gnm_datasets/scand/<sequence>.db3 \
        --output /home/favl/robotics/FleetSafe-VisualNav-Benchmark/data/gnm_datasets/scand_gnm/ \
        --camera-topic /usb_cam/image_raw \
        --odom-topic /odom

## Indoor vs Outdoor
SCAND contains both indoor (office corridors) and outdoor sequences.
Filter by sequence name prefix — indoor sequences are labelled in the
dataset's metadata CSV on the project page.

## Citation
Karnan, H., Nair, A., Xiao, X., Warnell, G., Pirk, S., Toshev, A., Hart, J., Biswas, J., & Stone, P. (2022). SCAND: A Large-Scale Dataset of Human-Driven Robot Navigation. RA-L 2022. https://arxiv.org/abs/2203.13924

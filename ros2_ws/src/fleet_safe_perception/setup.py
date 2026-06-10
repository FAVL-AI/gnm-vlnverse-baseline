from setuptools import setup, find_packages

package_name = "fleet_safe_perception"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(),
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="FAVL-AI",
    maintainer_email="frankleroyvan@gmail.com",
    description="Perception and safety processing for Fleet-Safe robots",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "imu_processor = fleet_safe_perception.imu_processor:main",
            "fleetsafe_perception = fleet_safe_perception.fleetsafe_perception_node:main",
        ],
    },
)

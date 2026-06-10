from setuptools import setup

package_name = "fleet_safe_control"

setup(
    name=package_name,
    version="0.1.0",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="FAVL-AI",
    maintainer_email="frankleroyvan@gmail.com",
    description="Fleet-Safe joint controller for H1",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "joint_controller = fleet_safe_control.joint_controller:main",
        ],
    },
)

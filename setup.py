"""GNM-VLNVerse Baseline package setup.

Install (editable mode, recommended for development):
    pip install -e .

Install (production):
    pip install .
"""
from setuptools import setup, find_packages

setup(
    name="gnm_vlnverse",
    version="0.1.0",
    description=(
        "Reproducible Isaac Sim pipeline for GNM visual-goal navigation on VLNVerse data"
    ),
    author="F. Van Laarhoven",
    author_email="F.Van-Laarhoven2@newcastle.ac.uk",
    packages=find_packages(include=["gnm_vlnverse", "gnm_vlnverse.*"]),
    python_requires=">=3.10",
    install_requires=[
        "torch>=2.2",
        "torchvision>=0.17",
        "timm>=0.9",
        "opencv-python-headless>=4.9",
        "numpy>=1.26,<2.0",
        "pyyaml>=6.0",
        "omegaconf>=2.3",
        "wandb>=0.17",
        "tqdm>=4.66",
        "scipy>=1.12",
        "pandas>=2.0",
    ],
    extras_require={
        "dev": ["pytest", "pytest-cov", "black", "isort"],
    },
    entry_points={
        "console_scripts": [
            "gnm-train=scripts.gnm.train_gnm_entry:main",
            "gnm-evaluate=scripts.gnm.eval_gnm_entry:main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
)

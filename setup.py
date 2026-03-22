import shutil
import platform
import sys
from pathlib import Path
from setuptools import setup

requirements = []

with open("requirements.txt") as f:
    for line in f:
        clean_line = line.strip()

        if clean_line and not clean_line.startswith("#"):
            requirements.append(clean_line)

setup(
    name="thumbs",
    version="1.0.0",
    package_dir={"": "src"},
    packages=[""],
    package_data={"": ["*.toml", "*.txt", "*.png"]},
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "thumbs = main:main",
        ],
    },
)
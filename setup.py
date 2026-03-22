import shutil
import platform
import sys
from pathlib import Path
from setuptools import setup
from src.info import info

requirements = []

with open("requirements.txt") as f:
    for line in f:
        clean_line = line.strip()

        if clean_line and not clean_line.startswith("#"):
            requirements.append(clean_line)

setup(
    name=info.name,
    version=info.version,
    package_dir={"": "src"},
    packages=[""],
    package_data={"": ["*.toml", "*.txt", "*.png"]},
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            f"{info.name} = main:main",
        ],
    },
)
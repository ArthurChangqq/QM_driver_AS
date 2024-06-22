from setuptools import find_packages, setup

with open("README.md", "r") as f:
    long_description = f.read()

setup(
    name="QM_driver_AS",
    version="0.0.10",
    description="An experimental data",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/shiau109/PYQUM_data",
    author="Li-Chieh, Hsiao",
    author_email="shiau109@gmail.com",
    license="MIT",
    classifiers=[
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.10",
        "Operating System :: OS Independent",
    ],
    install_requires=[
        "numpy>=1.26.0",
        "scipy>=1.13.0,",
        "matplotlib>=3.9",
        "xarray>=2024.6.0",
        "tomlkit>=0.12.5",
    ],
    # extras_require={
    #     "dev": ["pytest>=7.0", "twine>=4.0.2"],
    # },
    python_requires=">=3.10",
)
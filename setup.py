from os import path

from setuptools import setup


_here = path.dirname(__file__)

# Prevent spurious errors during `python setup.py test`, a la
# http://www.eby-sarna.com/pipermail/peak/2010-May/003357.html:
try:
    import multiprocessing

    multiprocessing = multiprocessing  # take it easy pyflakes
except ImportError:
    pass

setup(
    name="hashin",
    version="1.0.2",
    description="Edits your requirements.txt by hashing them in",
    long_description=open(path.join(_here, "README.rst")).read(),
    author="Peter Bengtsson",
    author_email="mail@peterbe.com",
    license="MIT",
    py_modules=["hashin"],
    entry_points={"console_scripts": ["hashin = hashin:main"]},
    url="https://github.com/peterbe/hashin",
    include_package_data=True,
    python_requires=">=3.9",
    install_requires=["packaging", "pip-api"],
    tests_require=["pytest"],
    setup_requires=["pytest-runner"],
    extras_require={"dev": ["tox", "twine"]},
    classifiers=[
        "Intended Audience :: Developers",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: 3 :: Only",
        "Topic :: Software Development :: Build Tools",
        "Topic :: System :: Installation/Setup",
        "Topic :: System :: Systems Administration",
    ],
    keywords=[
        "pip",
        "repeatable",
        "deploy",
        "deployment",
        "hash",
        "install",
        "installer",
    ],
)

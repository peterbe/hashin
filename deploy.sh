#!/usr/bin/env bash
set -eo pipefail

python setup.py sdist bdist_wheel upload

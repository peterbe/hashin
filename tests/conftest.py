import os
from tempfile import mkdtemp
from contextlib import contextmanager
from shutil import rmtree
from unittest import mock

import pytest


@pytest.fixture
def murlopen():
    with mock.patch("hashin.urlopen") as patch:
        yield patch


@pytest.fixture
def mock_get_parser():
    with mock.patch("hashin.get_parser") as patch:
        yield patch


@pytest.fixture
def mock_sys():
    with mock.patch("hashin.sys") as patch:
        yield patch


@pytest.fixture
def mock_run():
    with mock.patch("hashin.run") as patch:
        yield patch


@pytest.fixture
def tmpfile():
    @contextmanager
    def inner(name="requirements.txt"):
        dir_ = mkdtemp("hashintest")
        try:
            yield os.path.join(dir_, name)
        finally:
            rmtree(dir_)

    return inner

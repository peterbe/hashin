import argparse

from hashin import get_parser, DEFAULT_INDEX_URL


def test_everything():
    args = get_parser().parse_known_args(
        [
            "example",
            "another-example",
            "-r",
            "reqs.txt",
            "-a",
            "sha512",
            "-p",
            "3.5",
            "-v",
            "--dry-run",
            "--index-url",
            "https://pypi1.someorg.net/",
        ]
    )
    expected = argparse.Namespace(
        algorithm="sha512",
        packages=["example", "another-example"],
        python_version=["3.5"],
        requirements_file="reqs.txt",
        verbose=True,
        version=False,
        include_prereleases=False,
        dry_run=True,
        update_all=False,
        interactive=False,
        synchronous=False,
        index_url="https://pypi1.someorg.net/",
    )
    assert args == (expected, [])


def test_everything_long():
    args = get_parser().parse_known_args(
        [
            "example",
            "another-example",
            "--requirements-file",
            "reqs.txt",
            "--algorithm",
            "sha512",
            "--python-version",
            "3.5",
            "--verbose",
            "--dry-run",
            "--index-url",
            "https://pypi1.someorg.net/",
        ]
    )
    expected = argparse.Namespace(
        algorithm="sha512",
        packages=["example", "another-example"],
        python_version=["3.5"],
        requirements_file="reqs.txt",
        verbose=True,
        version=False,
        include_prereleases=False,
        dry_run=True,
        update_all=False,
        interactive=False,
        synchronous=False,
        index_url="https://pypi1.someorg.net/",
    )
    assert args == (expected, [])


def test_minimal():
    args = get_parser().parse_known_args(["example"])
    expected = argparse.Namespace(
        algorithm="sha256",
        packages=["example"],
        python_version=[],
        requirements_file="requirements.txt",
        verbose=False,
        version=False,
        include_prereleases=False,
        dry_run=False,
        update_all=False,
        interactive=False,
        synchronous=False,
        index_url=DEFAULT_INDEX_URL,
    )
    assert args == (expected, [])

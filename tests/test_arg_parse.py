import argparse

from hashin import parser


def test_everything():
    args = parser.parse_known_args([
        'example', 'another-example',
        '-r', 'reqs.txt',
        '-a', 'sha512',
        '-p', '3.5',
        '-v',
    ])
    expected = argparse.Namespace(
        algorithm='sha512',
        packages=['example', 'another-example'],
        python_version=['3.5'],
        requirements_file='reqs.txt',
        verbose=True,
        version=False,
    )
    assert args == (expected, [])


def test_everything_long():
    args = parser.parse_known_args([
        'example', 'another-example',
        '--requirements-file', 'reqs.txt',
        '--algorithm', 'sha512',
        '--python-version', '3.5',
        '--verbose',
    ])
    expected = argparse.Namespace(
        algorithm='sha512',
        packages=['example', 'another-example'],
        python_version=['3.5'],
        requirements_file='reqs.txt',
        verbose=True,
        version=False,
    )
    assert args == (expected, [])


def test_minimal():
    args = parser.parse_known_args(['example'])
    expected = argparse.Namespace(
        algorithm='sha256',
        packages=['example'],
        python_version=[],
        requirements_file='requirements.txt',
        verbose=False,
        version=False,
    )
    assert args == (expected, [])

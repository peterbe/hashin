#!/usr/bin/env python
"""
See README :)
"""

from __future__ import print_function
import cgi
import tempfile
import os
import re
import sys
import json
from itertools import chain

import pip

if sys.version_info >= (3,):
    from urllib.request import urlopen
else:
    from urllib import urlopen

    if sys.version_info < (2, 7, 9):
        import warnings
        warnings.warn(
            "In Python 2.7.9, the built-in urllib.urlopen() got upgraded "
            "so that it, by default, does HTTPS certificate verification. "
            "All prior versions do not. That means you run the risk of "
            "downloading from a server that claims (man-in-the-middle "
            "attack) to be https://pypi.python.org but actually is not. "
            "Consider upgrading your version of Python."
        )


major_pip_version = int(pip.__version__.split('.')[0])
if major_pip_version < 8:
    raise ImportError(
        "hashin only works with pip 8.x or greater"
    )


class PackageError(Exception):
    pass


def _verbose(*args):
    print('* ' + ' '.join(args))


def _download(url, binary=False):
    r = urlopen(url)
    if binary:
        return r.read()
    _, params = cgi.parse_header(r.headers.get('Content-Type', ''))
    encoding = params.get('charset', 'utf-8')
    return r.read().decode(encoding)


def run(spec, file, algorithm, python_versions=None, verbose=False):
    if '==' in spec:
        package, version = spec.split('==')
    else:
        assert '>' not in spec and '<' not in spec
        package, version = spec, None
        # then the latest version is in the breadcrumb

    data = get_package_data(package, verbose)
    if not version:
        version = get_latest_version(data)
        assert version
        if verbose:
            _verbose("Latest version for", version)

    try:
        releases = data['releases'][version]
    except KeyError:
        raise PackageError('No data found for version {0}'.format(version))

    if python_versions:
        releases = filter_releases(releases, python_versions)

    if not releases:
        if python_versions:
            raise PackageError(
                "No releases could be found for {0} matching Python versions {1}"
                .format(spec, python_versions)
            )
        else:
            raise PackageError(
                "No releases could be found for {0}"
                .format(spec, python_versions)
            )

    add_hashes(releases, algorithm, verbose=verbose)

    new_lines = ''
    new_lines = '{0}=={1} \\\n'.format(package, version)
    padding = ' ' * 4
    for i, release in enumerate(releases):
        new_lines += (
            '{0}--hash={1}:{2}'
            .format(padding, algorithm, release['hash'], release['url'])
        )
        if i != len(releases) - 1:
            new_lines += ' \\'
        new_lines += '\n'

    if verbose:
        _verbose("Editing", file)
    with open(file) as f:
        requirements = f.read()
    requirements = amend_requirements_content(
        requirements,
        package,
        new_lines
    )
    with open(file, 'w') as f:
        f.write(requirements)

    return 0


def amend_requirements_content(requirements, package, new_lines):
    # if the package wasn't already there, add it to the bottom
    if '%s==' % package not in requirements:
        # easy peasy
        if requirements:
            requirements = requirements.strip() + '\n'
        requirements += new_lines.strip() + '\n'
    else:
        # need to replace the existing
        lines = []
        padding = ' ' * 4
        for line in requirements.splitlines():
            if line.startswith('{0}=='.format(package)):
                lines.append(line)
            elif lines and line.startswith(padding):
                lines.append(line)
            elif lines:
                break
        combined = '\n'.join(lines + [''])
        requirements = requirements.replace(combined, new_lines)

    return requirements


def get_latest_version(data):
    return data['info']['version']


def expand_python_version(version):
    """
    Expand Python versions to all identifiers used on PyPI.

    >>> expand_python_version('3.5')
    ['3.5', 'py3', 'py2.py3', 'cp35']
    """
    if not re.match(r'^\d\.\d$', version):
        return [version]

    major, minor = version.split('.')
    patterns = [
        '{major}.{minor}',
        'cp{major}{minor}',
        'py{major}',
        'py{major}.{minor}',
        'source',
        'py2.py3',
    ]
    return set(pattern.format(major=major, minor=minor) for pattern in patterns)


# This should match the naming convention laid out in PEP 0427
# url = 'https://pypi.python.org/packages/3.4/P/Pygments/Pygments-2.1-py3-none-any.whl'
CLASSIFY_WHEEL_RE = re.compile('''
    ^(?P<package>.+)-
    (?P<version>\d[^-]*)-
    (?P<python_version>[^-]+)-
    (?P<abi>[^-]+)-
    (?P<platform>.+)
    .(?P<format>whl)
    (\#md5=.*)?
    $
''', re.VERBOSE)

CLASSIFY_EGG_RE = re.compile('''
    ^(?P<package>.+)-
    (?P<version>\d[^-]*)-
    (?P<python_version>[^-]+)
    (-(?P<platform>[^\.]+))?
    .(?P<format>egg)
    (\#md5=.*)?
    $
''', re.VERBOSE)

CLASSIFY_ARCHIVE_RE = re.compile('''
    ^(?P<package>.+)-
    (?P<version>\d[^-]*)
    .(?P<format>tar.(gz|bz2)|zip)
    (\#md5=.*)?
    $
''', re.VERBOSE)

CLASSIFY_EXE_RE = re.compile('''
    ^(?P<package>.+)-
    (?P<version>\d[^-]*)-
    ((?P<platform>[^-]*)-)?
    (?P<python_version>[^-]+)
    .(?P<format>exe)
    (\#md5=.*)?
    $
''', re.VERBOSE)


def release_url_metadata(url):
    filename = url.split('/')[-1]
    defaults = {
        'package': None,
        'version': None,
        'python_version': None,
        'abi': None,
        'platform': None,
        'format': None,
    }
    simple_classifiers = [CLASSIFY_WHEEL_RE, CLASSIFY_EGG_RE, CLASSIFY_EXE_RE]
    for classifier in simple_classifiers:
        match = classifier.match(filename)
        if match:
            defaults.update(match.groupdict())
            return defaults

    match = CLASSIFY_ARCHIVE_RE.match(filename)
    if match:
        defaults.update(match.groupdict())
        defaults['python_version'] = 'source'
        return defaults

    raise PackageError('Unrecognizable url: ' + url)


def filter_releases(releases, python_versions):
    python_versions = list(chain.from_iterable(expand_python_version(v) for v in python_versions))
    filtered = []
    for release in releases:
        metadata = release_url_metadata(release['url'])
        if metadata['python_version'] in python_versions:
            filtered.append(release)
    return filtered


def get_package_data(package, verbose=False):
    url = 'https://pypi.python.org/pypi/%s/json' % package
    if verbose:
        print(url)
    content = json.loads(_download(url))
    if 'releases' not in content:
        raise PackageError('package JSON is not sane')

    return content


def add_hashes(releases, algorithm, verbose=False):
    for found in releases:
        url = found['url']
        if verbose:
            _verbose("Found URL", url)
        download_dir = tempfile.gettempdir()
        filename = os.path.join(
            download_dir,
            os.path.basename(url.split('#')[0])
        )
        if not os.path.isfile(filename):
            if verbose:
                _verbose("  Downloaded to", filename)
            with open(filename, 'wb') as f:
                f.write(_download(url, binary=True))
        elif verbose:
            _verbose("  Re-using", filename)
        found['hash'] = pip.commands.hash._hash_of_file(filename, algorithm)
        if verbose:
            _verbose("  Hash", found['hash'])


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'package',
        help="package (e.g. some-package==1.2.3 or just some-package)"
    )
    parser.add_argument(
        'requirements_file',
        help="requirements file to write to (default requirements.txt)",
        default='requirements.txt', nargs='?'
    )
    parser.add_argument(
        'algorithm',
        help="The hash algorithm to use: one of sha256, sha384, sha512",
        default='sha256', nargs='?'
    )
    parser.add_argument(
        "-v, --verbose",
        help="Verbose output",
        action="store_true",
        dest='verbose',
    )
    parser.add_argument(
        '-p, --python-version',
        help='Python version to add wheels for. May be used multiple times.',
        action='append',
        default=[],
        dest='python_version',
    )

    args = parser.parse_args()
    return run(
        args.package,
        args.requirements_file,
        args.algorithm,
        args.python_version,
        verbose=args.verbose,
    )


if __name__ == '__main__':
    sys.exit(main())

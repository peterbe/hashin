#!/usr/bin/env python
"""
See README :)
"""

from __future__ import print_function
import cgi
import tempfile
import os
import sys
import json

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


def run(spec, file, algorithm, verbose=False):
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

    # needs to be turned into a list so we know its length
    hashes = list(get_hashes(data, version, algorithm, verbose=verbose))

    new_lines = ''
    new_lines = '{0}=={1} \\\n'.format(package, version)
    padding = ' ' * 4
    for i, h in enumerate(hashes):
        new_lines += '{0}--hash={1}:{2}'.format(padding, algorithm, h)
        if i != len(hashes) - 1:
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
            if '{0}=='.format(package) in line:
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


def get_package_data(package, verbose=False):
    url = 'https://pypi.python.org/pypi/%s/json' % package
    if verbose:
        print(url)
    content = json.loads(_download(url))
    if 'releases' not in content:
        raise PackageError('package JSON is not sane')

    return content


def get_hashes(data, version, algorithm, verbose=False):
    yielded = []
    try:
        releases = data['releases'][version]
    except KeyError:
        raise PackageError('No data found for version {0}'.format(version))
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
        hash_ = pip.commands.hash._hash_of_file(filename, algorithm)
        if hash_ in yielded:
            continue
        if verbose:
            _verbose("  Hash", hash_)
        yield hash_
        yielded.append(hash_)

    if not yielded:
        raise PackageError(
            "No packages could be found on {0}".format(url)
        )


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'package',
        help="package (e.g. some-package==1.2.3 or just some-package)"
    )
    parser.add_argument(
        'requirements_file',
        help="requirements file to write to (default requirementst.txt)",
        default='requirements.txt', nargs='?'
    )
    parser.add_argument(
        'algorithm',
        help="The hash algorithm to use: one of sha256, sha384, sha512",
        default='sha256', nargs='?'
    )
    parser.add_argument(
        "--verbose", help="Verbose output", action="store_true"
    )

    args = parser.parse_args()
    return run(
        args.package,
        args.requirements_file,
        args.algorithm,
        verbose=args.verbose,
    )


if __name__ == '__main__':
    sys.exit(main())

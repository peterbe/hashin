#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
See README :)
"""

from __future__ import print_function
import argparse
import cgi
import difflib
import tempfile
import os
import re
import sys
import json
from itertools import chain

import pip_api
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import parse

if sys.version_info >= (3,):
    from urllib.request import urlopen
    from urllib.error import HTTPError
else:
    from urllib import urlopen

    input = raw_input  # noqa

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

DEFAULT_ALGORITHM = "sha256"

major_pip_version = int(pip_api.version().split(".")[0])
if major_pip_version < 8:
    raise ImportError("hashin only works with pip 8.x or greater")


class PackageError(Exception):
    pass


class NoVersionsError(Exception):
    """When there are no valid versions found."""


class PackageNotFoundError(Exception):
    """When the package can't be found on pypi.org."""


def _verbose(*args):
    print("* " + " ".join(args))


def _download(url, binary=False):
    try:
        r = urlopen(url)
    except HTTPError as exception:
        status_code = exception.getcode()
        if status_code == 404:
            raise PackageNotFoundError(url)
        raise PackageError("Download error. {0} on {1}".format(status_code, url))

    # Note that urlopen will, by default, follow redirects.
    status_code = r.getcode()

    if 301 <= status_code < 400:
        location, _ = cgi.parse_header(r.headers.get("location", ""))
        if not location:
            raise PackageError(
                "No 'Location' header on {0} ({1})".format(url, status_code)
            )
        return _download(location)
    elif status_code == 404:
        raise PackageNotFoundError(url)
    elif status_code != 200:
        raise PackageError("Download error. {0} on {1}".format(status_code, url))
    if binary:
        return r.read()
    _, params = cgi.parse_header(r.headers.get("Content-Type", ""))
    encoding = params.get("charset", "utf-8")
    return r.read().decode(encoding)


def run(specs, requirements_file, *args, **kwargs):
    if not specs:  # then, assume all in the requirements file
        regex = re.compile(r"(^|\n|\n\r).*==")
        specs = []
        previous_versions = {}
        with open(requirements_file) as f:
            for line in f:
                if regex.search(line):
                    req = Requirement(line.split("\\")[0])
                    # Deliberately strip the specifier (aka. the version)
                    version = req.specifier
                    req.specifier = None
                    specs.append(str(req))
                    previous_versions[str(req).split(";")[0]] = version
        kwargs["previous_versions"] = previous_versions

    if isinstance(specs, str):
        specs = [specs]

    return run_packages(specs, requirements_file, *args, **kwargs)


def run_packages(
    specs,
    file,
    algorithm,
    python_versions=None,
    verbose=False,
    include_prereleases=False,
    dry_run=False,
    previous_versions=None,
    interactive=False,
):
    assert isinstance(specs, list), type(specs)
    all_new_lines = []
    first_interactive = True
    for spec in specs:
        restriction = None
        if ";" in spec:
            spec, restriction = [x.strip() for x in spec.split(";", 1)]
        if "==" in spec:
            package, version = spec.split("==")
        else:
            assert ">" not in spec and "<" not in spec
            package, version = spec, None
            # There are other ways to what the latest version is.

        req = Requirement(package)

        data = get_package_hashes(
            package=req.name,
            version=version,
            verbose=verbose,
            python_versions=python_versions,
            algorithm=algorithm,
            include_prereleases=include_prereleases,
        )
        package = data["package"]
        # We need to keep this `req` instance for the sake of turning it into a string
        # the correct way. But, the name might actually be wrong. Suppose the user
        # asked for "Django" but on PyPI it's actually called "django", then we want
        # correct that.
        # We do that by modifying only the `name` part of the `Requirement` instance.
        req.name = package

        new_version_specifier = SpecifierSet("=={}".format(data["version"]))

        if previous_versions and previous_versions.get(str(req)):
            # We have some form of previous version and a new version.
            # If they' already equal, just skip this one.
            if previous_versions[str(req)] == new_version_specifier:
                continue

        if interactive:
            try:
                if not interactive_upgrade_request(
                    package,
                    previous_versions[str(req)],
                    new_version_specifier,
                    print_header=first_interactive,
                ):
                    first_interactive = False
                    continue
                first_interactive = False
            except InteractiveAll:
                interactive = False
            except (InteractiveQuit, KeyboardInterrupt):
                return 1

        maybe_restriction = "" if not restriction else "; {0}".format(restriction)
        new_lines = "{0}=={1}{2} \\\n".format(req, data["version"], maybe_restriction)
        padding = " " * 4
        for i, release in enumerate(data["hashes"]):
            new_lines += "{0}--hash={1}:{2}".format(padding, algorithm, release["hash"])
            if i != len(data["hashes"]) - 1:
                new_lines += " \\"
            new_lines += "\n"
        all_new_lines.append((package, new_lines))

    if not all_new_lines:
        # This can happen if you use 'interactive' and said no to everything or
        # if every single package you listed already has the latest version.
        return 0

    with open(file) as f:
        old_requirements = f.read()
    requirements = amend_requirements_content(old_requirements, all_new_lines)
    if dry_run:
        if verbose:
            _verbose("Dry run, not editing ", file)
        print(
            "".join(
                difflib.unified_diff(
                    old_requirements.splitlines(True),
                    requirements.splitlines(True),
                    fromfile="Old",
                    tofile="New",
                )
            )
        )
    else:
        with open(file, "w") as f:
            f.write(requirements)
        if verbose:
            _verbose("Editing", file)

    return 0


class InteractiveAll(Exception):
    """When the user wants to say yes to ALL package updates."""


class InteractiveQuit(Exception):
    """When the user wants to stop the interactive update questions entirely."""


def interactive_upgrade_request(package, old_version, new_version, print_header=False):
    def print_version(v):
        return str(v).replace("==", "").ljust(15)

    if print_header:
        print(
            "PACKAGE".ljust(30),
            print_version("YOUR VERSION"),
            print_version("NEW VERSION"),
        )

    def print_line(checkbox=None):
        if checkbox is None:
            checkboxed = "?"
        elif checkbox:
            checkboxed = "✓"
        else:
            checkboxed = "✘"
        print(
            package.ljust(30),
            print_version(old_version),
            print_version(new_version),
            checkboxed,
        )

    print_line()

    def clear_line():
        sys.stdout.write("\033[F")  # Cursor up one line
        sys.stdout.write("\033[K")  # Clear to the end of line

    def ask():
        answer = input("Update? [Y/n/a/q]: ").lower().strip()
        if answer == "n":
            clear_line()
            clear_line()
            print_line(False)
            return False
        if answer == "a":
            clear_line()
            raise InteractiveAll
        if answer == "q":
            raise InteractiveQuit
        if answer == "y" or answer == "" or answer == "yes":
            clear_line()
            clear_line()
            print_line(True)
            return True
        return ask()

    return ask()


def amend_requirements_content(requirements, all_new_lines):
    # I wish we had types!
    assert isinstance(all_new_lines, list), type(all_new_lines)

    padding = " " * 4

    def is_different_lines(package, new_lines):
        # This assumes that for sure the package is already mentioned in the old
        # requirements. Now we just need to double-check that they really are
        # different.
        # The 'new_lines` is what we might intend to replace it with.
        lines = set()
        for line in requirements.splitlines():
            if regex.search(line):
                lines.add(line.strip(" \\"))
            elif lines and line.startswith(padding):
                lines.add(line.strip(" \\"))
            elif lines:
                break
        return lines != set([x.strip(" \\") for x in new_lines.splitlines()])

    for package, new_lines in all_new_lines:
        regex = re.compile(
            r"(^|\n|\n\r){0}==|(^|\n|\n\r){0}\[.*\]==".format(re.escape(package)),
            re.IGNORECASE,
        )
        # if the package wasn't already there, add it to the bottom
        if not regex.search(requirements):
            # easy peasy
            if requirements:
                requirements = requirements.strip() + "\n"
            requirements += new_lines.strip() + "\n"
        elif is_different_lines(package, new_lines):
            # need to replace the existing
            lines = []
            for line in requirements.splitlines():
                if regex.search(line):
                    lines.append(line)
                elif lines and line.startswith(padding):
                    lines.append(line)
                elif lines:
                    break
            combined = "\n".join(lines + [""])
            requirements = requirements.replace(combined, new_lines)

    return requirements


def get_latest_version(data, include_prereleases):
    """
    Return the version string of what we think is the latest version.
    In the data blob from PyPI there is the info->version key which
    is just the latest in time. Ideally we want the latest non-pre-release.
    """
    if not data.get("releases"):
        # If there were no releases, fall back to the old way of doing
        # things with the info->version key.
        # This feels kinda strange but it has worked for years
        return data["info"]["version"]
    all_versions = []
    count_prereleases = 0
    for version in data["releases"]:
        v = parse(version)
        if not v.is_prerelease or include_prereleases:
            all_versions.append((v, version))
        else:
            count_prereleases += 1
    all_versions.sort(reverse=True)
    if not all_versions:
        msg = "No valid version found."
        if not include_prereleases and count_prereleases:
            msg += (
                " But, found {0} pre-releases. Consider running again "
                "with the --include-prereleases flag.".format(count_prereleases)
            )
        raise NoVersionsError(msg)
    # return the highest non-pre-release version
    return str(all_versions[0][1])


def expand_python_version(version):
    """
    Expand Python versions to all identifiers used on PyPI.

    >>> expand_python_version('3.5')
    ['3.5', 'py3', 'py2.py3', 'cp35']
    """
    if not re.match(r"^\d\.\d$", version):
        return [version]

    major, minor = version.split(".")
    patterns = [
        "{major}.{minor}",
        "cp{major}{minor}",
        "py{major}",
        "py{major}.{minor}",
        "py{major}{minor}",
        "source",
        "py2.py3",
    ]
    return set(pattern.format(major=major, minor=minor) for pattern in patterns)


# This should match the naming convention laid out in PEP 0427
# url = 'https://pypi.python.org/packages/3.4/P/Pygments/Pygments-2.1-py3-none-any.whl' # NOQA
CLASSIFY_WHEEL_RE = re.compile(
    r"""
    ^(?P<package>.+)-
    (?P<version>\d[^-]*)-
    (?P<python_version>[^-]+)-
    (?P<abi>[^-]+)-
    (?P<platform>.+)
    .(?P<format>whl)
    (\#md5=.*)?
    $
""",
    re.VERBOSE,
)

CLASSIFY_EGG_RE = re.compile(
    r"""
    ^(?P<package>.+)-
    (?P<version>\d[^-]*)-
    (?P<python_version>[^-]+)
    (-(?P<platform>[^\.]+))?
    .(?P<format>egg)
    (\#md5=.*)?
    $
""",
    re.VERBOSE,
)

CLASSIFY_ARCHIVE_RE = re.compile(
    r"""
    ^(?P<package>.+)-
    (?P<version>\d[^-]*)
    (-(?P<platform>[^\.]+))?
    .(?P<format>tar.(gz|bz2)|zip)
    (\#md5=.*)?
    $
""",
    re.VERBOSE,
)

CLASSIFY_EXE_RE = re.compile(
    r"""
    ^(?P<package>.+)-
    (?P<version>\d[^-]*)[-\.]
    ((?P<platform>[^-]*)-)?
    (?P<python_version>[^-]+)
    .(?P<format>(exe|msi))
    (\#md5=.*)?
    $
""",
    re.VERBOSE,
)


def release_url_metadata(url):
    filename = url.split("/")[-1]
    defaults = {
        "package": None,
        "version": None,
        "python_version": None,
        "abi": None,
        "platform": None,
        "format": None,
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
        defaults["python_version"] = "source"
        return defaults

    raise PackageError("Unrecognizable url: " + url)


def filter_releases(releases, python_versions):
    python_versions = list(
        chain.from_iterable(expand_python_version(v) for v in python_versions)
    )
    filtered = []
    for release in releases:
        metadata = release_url_metadata(release["url"])
        if metadata["python_version"] in python_versions:
            filtered.append(release)
    return filtered


def get_package_data(package, verbose=False):
    url = "https://pypi.org/pypi/%s/json" % package
    if verbose:
        print(url)
    content = json.loads(_download(url))
    if "releases" not in content:
        raise PackageError("package JSON is not sane")

    return content


def get_releases_hashes(releases, algorithm, verbose=False):
    for found in releases:
        digests = found["digests"]
        try:
            found["hash"] = digests[algorithm]
            if verbose:
                _verbose("Found hash for", found["url"])
        except KeyError:
            # The algorithm is NOT in the 'digests' dict.
            # We have to download the file and use pip
            url = found["url"]
            if verbose:
                _verbose("Found URL", url)
            download_dir = tempfile.gettempdir()
            filename = os.path.join(download_dir, os.path.basename(url.split("#")[0]))
            if not os.path.isfile(filename):
                if verbose:
                    _verbose("  Downloaded to", filename)
                with open(filename, "wb") as f:
                    f.write(_download(url, binary=True))
            elif verbose:
                _verbose("  Re-using", filename)

            found["hash"] = pip_api.hash(filename, algorithm)
        if verbose:
            _verbose("  Hash", found["hash"])
        yield {"hash": found["hash"]}


def get_package_hashes(
    package,
    version=None,
    algorithm=DEFAULT_ALGORITHM,
    python_versions=(),
    verbose=False,
    include_prereleases=False,
):
    """
    Gets the hashes for the given package.

    >>> get_package_hashes('hashin')
    {
        'package': 'hashin',
        'version': '0.10',
        'hashes': [
            {
                'url': 'https://pypi.org/packages/[...]',
                'hash': '45d1c5d2237a3b4f78b4198709fb2ecf[...]'
            },
            {
                'url': 'https://pypi.org/packages/[...]',
                'hash': '0d63bf4c115154781846ecf573049324[...]'
            },
            {
                'url': 'https://pypi.org/packages/[...]',
                'hash': 'c32e6d9fb09dc36ab9222c4606a1f43a[...]'
            }
        ]
    }
    """
    data = get_package_data(package, verbose)
    if not version:
        version = get_latest_version(data, include_prereleases)
        assert version
        if verbose:
            _verbose("Latest version for {0} is {1}".format(package, version))

    # Independent of how you like to case type it, pick the correct
    # name from the PyPI index.
    package = data["info"]["name"]

    try:
        releases = data["releases"][version]
    except KeyError:
        raise PackageError("No data found for version {0}".format(version))

    if python_versions:
        releases = filter_releases(releases, python_versions)

    if not releases:
        if python_versions:
            raise PackageError(
                "No releases could be found for "
                "{0} matching Python versions {1}".format(version, python_versions)
            )
        else:
            raise PackageError("No releases could be found for {0}".format(version))

    hashes = list(
        get_releases_hashes(releases=releases, algorithm=algorithm, verbose=verbose)
    )
    return {"package": package, "version": version, "hashes": hashes}


def get_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "packages",
        help="One or more package specifiers (e.g. some-package or some-package==1.2.3)",
        nargs="*",
    )
    parser.add_argument(
        "-r",
        "--requirements-file",
        help="requirements file to write to (default requirements.txt)",
        default="requirements.txt",
    )
    parser.add_argument(
        "-a",
        "--algorithm",
        help="The hash algorithm to use: one of sha256, sha384, sha512",
        default=DEFAULT_ALGORITHM,
    )
    parser.add_argument("-v", "--verbose", help="Verbose output", action="store_true")
    parser.add_argument(
        "--include-prereleases",
        help="Include pre-releases (off by default)",
        action="store_true",
    )
    parser.add_argument(
        "-p",
        "--python-version",
        help="Python version to add wheels for. May be used multiple times.",
        action="append",
        default=[],
    )
    parser.add_argument(
        "--version", help="Version of hashin", action="store_true", default=False
    )
    parser.add_argument(
        "--dry-run",
        help="Don't touch requirements.txt and just show the diff",
        action="store_true",
        default=False,
    )
    parser.add_argument(
        "-u",
        "--update-all",
        help="Update all mentioned packages in the requirements file.",
        action="store_true",
        default=False,
    )
    parser.add_argument(
        "-i",
        "--interactive",
        help=(
            "Ask about each possible update. "
            "Only applicable together with --update-all/-u."
        ),
        action="store_true",
        default=False,
    )
    return parser


def main():
    if "--version" in sys.argv[1:]:
        # Can't be part of argparse because the 'packages' is mandatory
        # print out the version of self
        import pkg_resources

        print(pkg_resources.get_distribution("hashin").version)
        return 0

    parser = get_parser()
    args = parser.parse_args()

    if args.update_all:
        if args.packages:
            print(
                "Can not combine the --update-all option with a list of packages.",
                file=sys.stderr,
            )
            return 2
    elif args.interactive:
        print(
            "--interactive (or -i) is only applicable together "
            "with --update-all (or -u).",
            file=sys.stderr,
        )
        return 4
    elif not args.packages:
        print("If you don't use --update-all you must list packages.", file=sys.stderr)
        parser.print_usage()
        return 3

    try:
        return run(
            args.packages,
            args.requirements_file,
            args.algorithm,
            args.python_version,
            verbose=args.verbose,
            include_prereleases=args.include_prereleases,
            dry_run=args.dry_run,
            interactive=args.interactive,
        )
    except PackageError as exception:
        print(str(exception), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

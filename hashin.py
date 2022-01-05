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
import concurrent.futures

import pip_api
from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import parse

if sys.version_info >= (3,):
    from urllib.request import urlopen
    from urllib.error import HTTPError
    from urllib.parse import urljoin
else:
    from urllib import urlopen
    from urlparse import urljoin

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

DEFAULT_INDEX_URL = os.environ.get("INDEX_URL", "https://pypi.org/")
assert DEFAULT_INDEX_URL

MAX_WORKERS = None

if sys.version_info >= (3, 4) and sys.version_info < (3, 5):
    # Python 3.4 is an odd duck. It's the first Python 3 version that had
    # concurrent.futures.ThreadPoolExecutor built in. (Python 2.7 needs a
    # backport from PyPI)
    # However, in Python 3.4 the max_workers (first and only argument) needs
    # to be set. In version > 3.4 the max_workers argument can be None and
    # it will itself figure it out by figuring out the systems number of
    # CPUs and then multiplying that number by 5.
    # So, exclusively for 3.4 we have to set this to some integer.
    # Python 3.4 is small so it's not important that it's the perfect amount.
    MAX_WORKERS = 5

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
                if regex.search(line) and not line.lstrip().startswith("#"):
                    req = Requirement(line.split("\\")[0])
                    # Deliberately strip the specifier (aka. the version)
                    version = req.specifier
                    req.specifier = None
                    specs.append(str(req))
                    previous_versions[str(req)] = version
        kwargs["previous_versions"] = previous_versions

    if isinstance(specs, str):
        specs = [specs]

    return run_packages(specs, requirements_file, *args, **kwargs)


def _explode_package_spec(spec):
    restriction = None
    if ";" in spec:
        spec, restriction = [x.strip() for x in spec.split(";", 1)]
    if "==" in spec:
        package, version = spec.split("==")
    else:
        assert ">" not in spec and "<" not in spec
        package, version = spec, None
    return package, version, restriction


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
    synchronous=False,
    index_url=DEFAULT_INDEX_URL,
):
    assert index_url
    assert isinstance(specs, list), type(specs)
    all_new_lines = []
    first_interactive = True
    yes_to_all = False

    lookup_memory = {}
    if not synchronous and len(specs) > 1:
        pre_download_packages(
            lookup_memory, specs, verbose=verbose, index_url=index_url
        )

    for spec in specs:
        package, version, restriction = _explode_package_spec(spec)

        # It's important to keep a track of what the package was called before
        # so that if we have to amend the requirements file, we know what to
        # look for before.
        previous_name = package

        # The 'previous_versions' dict is based on the old names. So figure
        # out what the previous version was *before* the new/"correct" name
        # is figured out.
        previous_version = previous_versions.get(package) if previous_versions else None

        req = Requirement(package)

        data = get_package_hashes(
            package=req.name,
            version=version,
            verbose=verbose,
            python_versions=python_versions,
            algorithm=algorithm,
            include_prereleases=include_prereleases,
            lookup_memory=lookup_memory,
            index_url=index_url,
        )
        package = data["package"]
        # We need to keep this `req` instance for the sake of turning it into a string
        # the correct way. But, the name might actually be wrong. Suppose the user
        # asked for "Django" but on PyPI it's actually called "django", then we want
        # correct that.
        # We do that by modifying only the `name` part of the `Requirement` instance.
        req.name = package

        if previous_versions is None:
            # Need to be smart here. It's a little counter-intuitive.
            # If no previous_versions was supplied that has an implied the fact;
            # the user was explicit about what they want to install.
            # The name it was called in the old requirements file doesn't matter.
            previous_name = package

        new_version_specifier = SpecifierSet("=={}".format(data["version"]))

        if previous_version:
            # We have some form of previous version and a new version.
            # If they' already equal, just skip this one.
            if previous_version == new_version_specifier:
                continue

        if interactive:
            try:
                response = interactive_upgrade_request(
                    package,
                    previous_version,
                    new_version_specifier,
                    print_header=first_interactive,
                    force_yes=yes_to_all,
                )
                first_interactive = False
                if response == "NO":
                    continue
                elif response == "ALL":
                    # If you ever answer "all" to the update question, we don't want
                    # stop showing the interactive prompt but we don't need to
                    # ask any questions any more. This way, you get to see the
                    # upgrades that are going to happen.
                    yes_to_all = True
                elif response == "QUIT":
                    return 1
            except KeyboardInterrupt:
                return 1

        maybe_restriction = "" if not restriction else "; {0}".format(restriction)
        new_lines = "{0}=={1}{2} \\\n".format(req, data["version"], maybe_restriction)
        padding = " " * 4
        for i, release in enumerate(sorted(data["hashes"], key=lambda r: r["hash"])):
            new_lines += "{0}--hash={1}:{2}".format(padding, algorithm, release["hash"])
            if i != len(data["hashes"]) - 1:
                new_lines += " \\"
            new_lines += "\n"
        all_new_lines.append((package, previous_name, new_lines))

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


def pre_download_packages(memory, specs, verbose=False, index_url=DEFAULT_INDEX_URL):
    futures = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for spec in specs:
            package, _, _ = _explode_package_spec(spec)
            req = Requirement(package)
            futures[
                executor.submit(get_package_data, req.name, index_url, verbose=verbose)
            ] = req.name
        for future in concurrent.futures.as_completed(futures):
            content = future.result()
            memory[futures[future]] = content


def interactive_upgrade_request(
    package, old_version, new_version, print_header=False, force_yes=False
):
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

    if force_yes:
        print_line(True)
        return "YES"
    else:
        print_line()

    printed_help = []

    def print_help():
        print(
            "y - Include this update (default)\n"
            "n - Skip this update\n"
            "a - Include this and all following upgrades\n"
            "q - Skip this and all following upgrades\n"
            "? - Print this help\n"
        )
        printed_help.append(1)

    def clear_line():
        sys.stdout.write("\033[F")  # Cursor up one line
        sys.stdout.write("\033[K")  # Clear to the end of line

    def ask():
        answer = input("Update? [Y/n/a/q/?]: ").lower().strip()
        if printed_help:
            # Because the print_help() prints 5 lines to stdout.
            # Plus 2 because of the original question line and the extra blank line.
            for i in range(5 + 2):
                clear_line()
            # printed_help.clear()
            del printed_help[:]

        if answer == "n":
            clear_line()
            clear_line()
            print_line(False)
            return "NO"
        if answer == "a":
            clear_line()
            clear_line()
            print_line(True)
            return "ALL"
        if answer == "q":
            return "QUIT"
        if answer == "y" or answer == "" or answer == "yes":
            clear_line()
            clear_line()
            print_line(True)
            return "YES"
        if answer == "?":
            print_help()

        return ask()

    return ask()


def amend_requirements_content(requirements, all_new_lines):
    # I wish we had types!
    assert isinstance(all_new_lines, list), type(all_new_lines)

    padding = " " * 4

    def is_different_lines(old_lines, new_lines, indent):
        # This regex is used to only temporarily normalize the names of packages
        # in the lines being compared. This results in "old" names matching
        # "new" names so that hashin correctly replaces them when it looks for
        # them.
        match_delims = re.compile(r"[-_]")

        # This assumes that the package is already mentioned in the old
        # requirements. Now we just need to double-check that its lines are
        # different.
        # The 'new_lines` is what we might intend to replace it with.
        old = set([match_delims.sub("-", line.strip(" \\")) for line in old_lines])
        new = set([indent + x.strip(" \\") for x in new_lines])
        return old != new

    for package, old_name, new_text in all_new_lines:
        # The call to `escape` will turn hyphens into escaped hyphens
        #
        # ex.
        #   -       becomes     \\-
        #
        escaped = re.escape(old_name)

        # This changes those escaped hypens into a pattern to match
        #
        # ex.
        #   \\-     becomes     [-_]
        #
        # This is necessary so that hashin will correctly find underscored (old)
        # and hyphenated (new) package names so that it will correctly replace an
        # old name with the new name when there is a version update.
        escape_replaced = escaped.replace("\\-", "[-_]")
        regex = re.compile(
            r"^(?P<indent>[ \t]*){0}(\[.*\])?==".format(escape_replaced),
            re.IGNORECASE | re.MULTILINE,
        )
        # if the package wasn't already there, add it to the bottom
        match = regex.search(requirements)
        if not match:
            # easy peasy
            if requirements:
                requirements = requirements.strip() + "\n"
            requirements += new_text.strip() + "\n"
        else:
            indent = match.group("indent")
            lines = []
            for line in requirements.splitlines():
                if regex.search(line):
                    lines.append(line)
                elif lines and line.startswith(indent + padding + "#"):
                    break
                elif lines and line.startswith(indent + padding):
                    lines.append(line)
                elif lines:
                    break
            if is_different_lines(lines, new_text.splitlines(), indent):
                # need to replace the existing
                combined = "\n".join(lines + [""])
                # indent non-empty lines
                indented = re.sub(
                    r"^(.+)$", r"{0}\1".format(indent), new_text, flags=re.MULTILINE
                )
                requirements = requirements.replace(combined, indented)

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


def get_package_data(package, index_url, verbose=False):
    path = "/pypi/%s/json" % package
    url = urljoin(index_url, path)
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
    lookup_memory=None,
    index_url=DEFAULT_INDEX_URL,
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
    if lookup_memory is not None and package in lookup_memory:
        data = lookup_memory[package]
    else:
        data = get_package_data(package, index_url, verbose)
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
        "-d",
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
    parser.add_argument(
        "--synchronous",
        help="Do not download from pypi in parallel.",
        action="store_true",
        default=False,
    )
    parser.add_argument(
        "--index-url",
        help="alternate package index url (default {0})".format(DEFAULT_INDEX_URL),
        default=DEFAULT_INDEX_URL,
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

    if (
        args.update_all
        and args.packages
        and len(args.packages) == 1
        and os.path.isfile(args.packages[0])
        and args.packages[0].endswith(".txt")
    ):
        # It's totally common to make the mistake of using the `--update-all` flag
        # and specifying the requirements file as the first argument. E.g.
        #
        #     $ hashin --update-all --interactive myproject/reqs.txt
        #
        # The user intention is clear any non-keyed flags get interpreted as a
        # list of "packages". Let's fix that for the user.
        args.requirements_file = args.packages[0]
        args.packages = []

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
            synchronous=args.synchronous,
            index_url=args.index_url,
        )
    except PackageError as exception:
        print(str(exception), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

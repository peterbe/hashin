======
hashin
======

.. image:: https://github.com/peterbe/hashin/workflows/Python/badge.svg
    :target: https://github.com/peterbe/hashin/actions

.. image:: https://badge.fury.io/py/hashin.svg
    :target: https://pypi.python.org/pypi/hashin

Helps you write your ``requirements.txt`` with hashes so you can
install with ``pip install --require-hashes -r ...``

If you want to add a package or edit the version of one you're currently
using you have to do the following steps:

1. Go to pypi for that package
2. Download the ``.tgz`` file
3. Possibly download the ``.whl`` file
4. Run ``pip hash downloadedpackage-1.2.3.tgz``
5. Run ``pip hash downloadedpackage-1.2.3.whl``
6. Edit ``requirements.txt``

This script does all those things.
Hackishly wonderfully so.

A Word of Warning!
==================

The whole point of hashing is that you **vet the packages** that you use
on your laptop and that they haven't been tampered with. Then you
can confidently install them on a server.

This tool downloads from PyPI (over HTTPS) and runs ``pip hash``
on the downloaded files.

You should check that the packages that are downloaded
are sane and not tampered with. The way you do that is to run
``hashin`` as normal but with the ``--verbose`` flag. When you do that
it will print where it downloaded the relevant files and those
files are not deleted. For example::

    $ hashin --verbose bgg /tmp/reqs.txt
    https://pypi.python.org/pypi/bgg/json
    * Latest version for 0.22.1
    * Found URL https://pypi.python.org/packages/2.7/b/bgg/bgg-0.22.1-py2-none-any.whl
    *   Re-using /var/folders/1x/2hf5hbs902q54g3bgby5bzt40000gn/T/bgg-0.22.1-py2-none-any.whl
    *   Hash e5172c3fda0e8a42d1797fd1ff75245c3953d7c8574089a41a219204dbaad83d
    * Found URL https://pypi.python.org/packages/source/b/bgg/bgg-0.22.1.tar.gz
    *   Re-using /var/folders/1x/2hf5hbs902q54g3bgby5bzt40000gn/T/bgg-0.22.1.tar.gz
    *   Hash aaa53aea1cecb8a6e1288d6bfe52a51408a264a97d5c865c38b34ae16c9bff88
    * Editing /tmp/reqs.txt

You might not have time to go through the lines one by one
but you should be aware that the vetting process is your
responsibility.

Installation
============

This is something you only do or ever need in a development
environment. Ie. your laptop::

    pip install hashin

How to use it
=============

Suppose you want to install ``futures``. You can either do this::

    hashin futures

Which will download the latest version tarball (and wheel) and
calculate their pip hash and edit your ``requirements.txt`` file.

Or you can be specific about exactly which version you want::

    hashin "futures==2.1.3"

You can also specify more than one package at a time::

    hashin "futures==2.1.3" requests

Suppose you don't have a ``requirements.txt`` right there in the same
directory you can specify ``--requirements-file``::

    hashin futures --requirements-file=stuff/requirements/prod.txt

By default ``sha256`` hashes are used, but this can be overridden using the
``--algorithm`` argument::

    hashin futures --algorithm=sha512

If there's no output, it worked. Check how it edited your
requirements file.

Filtering releases by Python version
====================================

Some requirements have many releases built for different versions of Python and
different architectures. These hashes aren't useful in some cases, if those
wheels don't work with your project. ``hashin`` can filter on the Python
version to skip these extraneous hashes.

For example, the ``cffi`` package offers wheels built for many versions of
CPython from 2.6 to 3.5. To select only one of them, you can use the
``--python-version`` option::

    hashin "cffi==1.5.2" --python-version 3.5

If you need to support multiple versions, you can pass this option multiple
times::

    hashin "cffi==1.5.2" --python-version 2.7 --python-version 3.5

``hashin`` will expand these Python versions to a full list of identifers that
could be found on PyPI. For example, ``3.5`` will expand to match any of
``3.5``, ``py3``, ``py3.5``, ``py2.py3``, or ``cp3.5``. You can also specify
these exact identifiers directly, if you need something specific.

The ``source`` release is always automatically included. ``pip`` will use
this as a fallback in the case a suitable wheel cannot be found.

Dry run mode
============

There are some use cases, when you maybe don't want to edit your ``requirements.txt``
right away. You can use the ``--dry-run`` argument to show the diff, so you
can preview the changes to your ``requirements.txt`` file.

Example::

    hashin --dry-run requests==2.19.1

Would result in a printout on the command line::

    --- Old
    +++ New
    @@ -0,0 +1,3 @@
    +requests==2.19.1 \
    +    --hash=sha256:63b52e3c866428a224f97cab011de738c36aec0185aa91cfacd418b5d58911d1 \
    +    --hash=sha256:ec22d826a36ed72a7358ff3fe56cbd4ba69dd7a6718ffd450ff0e9df7a47ce6a

PEP-0496 Environment Markers
============================

Requirements can use `PEP-0496`_ style specifiers (e.g. like
``cffi==1.5.2; python_version >= '3.4'``) and these will be passed
through when re-writing the ``requirements.txt`` file. ``hashin`` doesn't
parse the specifiers themselves and will take anything after the
semicolon. If you are using ``python_version`` you will still need to
pass appropriate options if you don't want every available hash.

An example of this might be::

    hashin "pywin32-ctypes ; sys_platform == 'win32'"

which will result it something like this in the ``requirements.txt`` file::

    pywin32-ctypes==0.1.2; sys_platform == 'win32' \
        --hash=sha256:4820b830f42e6889d34142bcd07b3896018c3620d8c31f5e13b72caf1f4d1d0f

And if you want to limit it to certain Python versions, here's an example::

    hashin "cffi==1.5.2; python_version >= '3.4'" -p 3.4 -p 3.5


.. _`PEP-0496`: https://www.python.org/dev/peps/pep-0496/

Using as a Python library
=========================

Everything you can do with ``hashin`` on the command line you can do
in running Python too. For example::

    import hashin
    from pprint import pprint
    pprint(hashin.get_package_hashes('Django'))

This will print out::

    {'hashes': [{'hash': 'fbc7ffaa45a4a67cb45f77dbd94e8eceecebe1d0959fe9c665dfbf28b41899e6',
             'url': 'https://pypi.python.org/packages/41/c1/68dd27946b03a3d756b0ff665baad25aee1f59918891d86ab76764209208/Django-1.11b1-py2.py3-none-any.whl'}],
    'package': 'Django',
    'version': '1.11b1'}

Or with specific version, algorithm and certain Python versions::

    import hashin
    from pprint import pprint
    pprint(hashin.get_package_hashes(
        'Django',
        version='1.10',
        algorithm='sha512',
        python_versions=('3.5',)
    ))

Local development
=================

After you have cloned the project, created a virtual environment and run:

    pip install -e ".[dev]"

Now, to run it you can use the installed executable ``hashin`` and do things
like::

    touch /tmp/reqs.txt
    hashin -r /tmp/reqs.txt Django


Running tests
=============

Simply run::

    python setup.py test

When you use ``pip install ".[dev]"`` it will install ``tox`` which you can use
to run the full test suites (plus linting) in different Python environments::

    tox

Running tests with test coverage
================================

To run the tests with test coverage, with ``pytest`` run something like
this::

    $ pip install pytest-cover
    $ pytest --cov=hashin --cov-report=html
    $ open htmlcov/index.html


Debugging
=========

To avoid having to install ``hashin`` just to test it or debug a feature
you can simply just run it like this::

    touch /tmp/whatever.txt
    python hashin.py --verbose Django /tmp/whatever.txt


Code Style
==========

All Python code should be run through `Black <https://pypi.org/project/black/>`_.
This is checked in CI and you can test it locally with ``tox``.

Also, this project uses `pre-commit <https://pre-commit.com/>`_
which helps with checking code style as a git pre-commit hook. ``pre-commit``
is used in ``tox``. To run all code style checks, use ``tox -e lint`` but
make sure your version of ``tox`` is built on a Python 3.

History
=======

This program is a "fork" of https://pypi.python.org/pypi/peepin
``peepin`` was a companion to the program ``peep``
https://pypi.python.org/pypi/peep/ but the functionality of ``peep``
has been put directly into ``pip`` as of version 8.

Future
======

If this script proves itself to work and be useful, I hope we can
put it directly into ``pip``.

Version History
===============

1.0.5
  * Make ``setup.py sdist`` ship missing file ``tests/conftest.py``.
    See https://github.com/peterbe/hashin/issues/217
    and https://github.com/peterbe/hashin/pull/220 — thanks @hartwork

  * Drop deprecated trove license classifier from ``setup.py``.
    See https://github.com/peterbe/hashin/pull/218 — thanks @hartwork

  * Resolve gone option ``tests_require`` from ``setup.py``.
    See https://github.com/peterbe/hashin/pull/219 — thanks @hartwork

1.0.4
  * Resolve dependency on pip-api.
    See https://github.com/peterbe/hashin/pull/214 — thanks @hartwork

  * Drop pytest-runner from ``setup_requires`` in ``setup.py``.
    See https://github.com/peterbe/hashin/pull/215 — thanks @hartwork

1.0.3
  * Drop support for Pythom 3.8.
    See https://github.com/peterbe/hashin/pull/192 — thanks @hartwork

  * Add support for Python 3.13.
    See https://github.com/peterbe/hashin/pull/195
    and https://github.com/peterbe/hashin/pull/204
    — thanks @pib and @hartwork

  * Be robust towards invalid versions like ``0.3.2d`` when finding
    the latest release.
    See https://github.com/peterbe/hashin/pull/196 — thanks @hartwork

1.0.2
  * Fix command line argument ``-p PYTHON_VERSION``
    (and API function ``expand_python_version``) for "3.10" and upwards
    See https://github.com/peterbe/hashin/pull/186

1.0.1
  * Update change log about the 1.0.0 release.

1.0.0
  * Update ``setup.py``, ``tox.ini`` and GitHub Actions to use Python ``>=3.8``
    and up to 3.12.

0.17.0
  * Add python 3.9 and 3.10 to the test matrix.

  * Preserve lexigraphical order of hashes for the output of the
    ``get_releases_hashes`` function.
    See https://github.com/peterbe/hashin/issues/126

0.16.0
  * Preserve indented comments when updating requirements files.
    See https://github.com/peterbe/hashin/issues/124

  * Switch to GitHub Actions instead of TravisCI. And test ``tox`` in
    Python 3.7 and 3.8 additionally as well as upgrading lint requirements.
    See https://github.com/peterbe/hashin/pull/118

0.15.0
  * Use of underscore or hyphens in package names is corrected
    See https://github.com/peterbe/hashin/issues/116 Thanks @caphrim007

0.14.6
  * Indentation in the requirements file is preserved.
    See https://github.com/peterbe/hashin/issues/112 Thanks @techtonik

  * If you use ``--update-all`` and forget the ``-r`` when specifying your
    requirements file, instead of complaining, it corrects the intentions.
    See https://github.com/peterbe/hashin/issues/104

0.14.5
  * When writing down hashes, they are now done in a lexigraphically ordered
    way. This makes the writes to the requirements file more predictable.
    See https://github.com/peterbe/hashin/issues/105

0.14.4
  * Bugfix for new ``--index-url`` option feature in version 0.14.3.
    See https://github.com/peterbe/hashin/issues/108

0.14.3
  * New parameter ``--index-url`` which allows to override the default which
    is ``https://pypi.org``. Thanks @nmacinnis
    See https://github.com/peterbe/hashin/pull/107

0.14.2
  * When using ``--update-all`` and parsing requirements file it could be fooled
    by comments that look like package specs (e.g ``# check out foo==1.0``)
    See https://github.com/peterbe/hashin/issues/103

0.14.1
  * All HTTP GET work to fetch information about packages from PyPI is done in
    concurrent threads. Requires backport for Python 2.7.
    See https://github.com/peterbe/hashin/issues/101

0.14.0
  * ``--interactive`` (when you use ``--update-all``) will iterate over all outdated
    versions in your requirements file and ask, for each one, if you want to
    updated it.
    See https://github.com/peterbe/hashin/issues/90

  * Order of hashes should not affect if a package in the requirements file
    should be replaced or not.
    See https://github.com/peterbe/hashin/issues/93

  * (Internal) All tests have been rewritten as plain pytest functions.

  * In Python 3, if the package can't be found you get a more explicit exception
    pointing out which package (URL) that failed.
    See https://github.com/peterbe/hashin/issues/87

  * New flag ``--update-all`` (alias ``-u``) will parse the requirements file,
    ignore the version, and update all packages that have new versions.
    See https://github.com/peterbe/hashin/pull/88

  * Support for "extras syntax". E.g. ``hashin "requests[security]"``. Doesn't
    actually get hashes for ``security`` (in this case, that's not even a
    package) but allows that syntax into your ``requirements.txt`` file.
    See https://github.com/peterbe/hashin/issues/70

  * All code is now formatted with `Black <https://pypi.org/project/black/>`_.

0.13.4
  * Ability to pass ``--dry-run`` which prints a diff of what it *would*
    do to your requirements file. See https://github.com/peterbe/hashin/pull/78

  * Better error message when no versions, but some pre-releases found.
    See https://github.com/peterbe/hashin/issues/76

  * Don't show URLs when using ``--verbose`` if files don't need to be
    downloaded. See https://github.com/peterbe/hashin/issues/73

0.13.3
  * Makes it possible to install ``nltk`` on Windows.
    `Thanks @chrispbailey! <https://github.com/peterbe/hashin/pull/72>`_

0.13.2
  * Match Python versions as ``py{major}{minor}`` additionally. Solves
    problem with installing packages with files like
    ``Paste-2.0.3-py34-none-any.whl``.
    `Thanks @danfoster! <https://github.com/peterbe/hashin/pull/67>`_

0.13.1
  * Ability to pass ``--include-prereleases`` if you're trying to add
    a package that *only* has pre-releases.

0.13.0
  * Two new dependencies for ``hashin``: ``pip-api`` and ``packaging``.
    This means we no longer need to *import* ``pip`` and rely on private
    APIs.
    `Thanks @di! <https://github.com/peterbe/hashin/pull/59>`_
    This also means you can no longer install ``hashin`` on Python 2.6 and
    Python ``<=3.3``.

0.12.0
  * Switch from ``pypi.python.org/pypi/<package>/json`` to
    ``pypi.org/pypi/<package>/json`` which also means the sha256 hash is part
    of the JSON payload immediately instead of having to download and run
    ``pip`` to get the hash.

  * Testing no runs Python 2.6 and Python 3.3.

  * All hashes, per package, are sorted (by the hash) to make it more
    predictable.

0.11.5
  * You can now pass PEP-0496 Environment Markers together with the package
    name, and they get passed into the ``requirements.txt`` file.
    Thanks @meejah

0.11.4
  * PackageErrors happening in CLI suppressed just the error message out on
    stderr. No full traceback any more.

0.11.3
  * Better error if you typo the package name since it'll 404 on PyPI.

0.11.2
  * Run continuous integration tests with Python 3.6 too.

0.11.1
  * Ability to run ``hashin --version`` to see what version of hashin is
    installed.
    See https://github.com/peterbe/hashin/issues/41

0.11.0
  * Cope with leading zeros in version numbers when figuring out what
    the latest version is.
    See https://github.com/peterbe/hashin/issues/39

0.10.0
  * Latest version is now figured out by looking at all version numbers
    in the list of releases from the JSON payload. The pre releases are
    skipped.

0.9.0
  * Fixed a bug where it would fail to install a package whose name is
    partially part of an existing (installed) package.
    E.g. installing ``redis==x.y.z`` when ``django-redis==a.b.c`` was
    already in the requirements file.

0.8.0
  * Ability to make ``hashin`` work as a library. Thanks @jayfk !

  * pep8 cleanups.

0.7.2
  * Fixes bug related to installing platform specific archives
    See https://github.com/peterbe/hashin/pull/33 Thanks @mythmon

0.7.1
  * Package matching is now case insensitive. E.g. ``hashin dJaNgO``

0.7.0
  * The requirements file and algorithm arguments are now keyword
    arguments. Now, the second, third, nth positional argument are
    additional arguments. Thanks @https://github.com/ahal

0.6.1
  * Support windows binaries packaged as a ``.msi`` file.

0.6.0
  * Fix compatibility issue with pip 8.1.2 and 8.1.1-2ubuntu0.1 and drop
    support for Python 2.6

0.5.0
  * Important bug fix. As an example, if you had ``pytest-selenium==...``
    already in your ``requirements.txt`` file and add ``selenium==x.y.z``
    it would touch the line with ``pytest-selenium`` too.

0.4.1
  * Support for PyPI links that have a hash in the file URL.

0.4.1
  * Fix PackageError if no Python version is defined.

0.4
  * Add filtering of package releases by Python version.

0.3
  * Issue a warning for users of Python before version 2.7.9.

0.2
  * Last character a *single* newline. Not two.

0.1
  * First, hopefully, working version.

======
hashin
======

.. image:: https://travis-ci.org/peterbe/hashin.svg?branch=master
    :target: https://travis-ci.org/peterbe/hashin

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

Suppose you don't have a ``requirements.txt`` right there in the same
directory you can do this::

    hashin "futures==2.1.3" stuff/requirementst/prod.txt

If there's not output. It worked. Check how it edited your
requirements files.

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

Runnings tests
==============

Simply run::

    python setup.py test


Debugging
=========

To avoid having to install ``hashin`` just to test it or debug a feature
you can simply just run it like this::

    touch /tmp/whatever.txt
    python hashin.py --verbose Django /tmp/whatever.txt


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

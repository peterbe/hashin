import sys
import json
import os
from shutil import rmtree
from tempfile import mkdtemp, gettempdir
from contextlib import contextmanager
from unittest import TestCase
from functools import wraps
from glob import glob

import mock

import hashin


if sys.version_info >= (3,):
    # As in, Python 3
    from io import StringIO
    STR_TYPE = str
else:  # Python 2
    from StringIO import StringIO


@contextmanager
def redirect_stdout(stream):
    import sys
    sys.stdout = stream
    yield
    sys.stdout = sys.__stdout__


@contextmanager
def tmpfile(name='requirements.txt'):
    dir_ = mkdtemp('hashintest')
    try:
        yield os.path.join(dir_, name)
    finally:
        rmtree(dir_)


def cleanup_tmpdir(pattern):

    def decorator(test):
        @wraps(test)
        def inner(self, *args, **kwargs):
            try:
                return test(self, *args, **kwargs)
            finally:
                for each in glob(os.path.join(gettempdir(), pattern)):
                    os.remove(each)
        return inner
    return decorator


class _Response(object):
    def __init__(self, content, status_code=200, headers=None):
        if isinstance(content, dict):
            content = json.dumps(content).encode('utf-8')
        self.content = content
        self.status_code = status_code
        if headers is None:
            headers = {'Content-Type': 'text/html'}
        self.headers = headers

    def read(self):
        return self.content


class Tests(TestCase):

    @mock.patch('hashin.urlopen')
    def test_get_latest_version_simple(self, murlopen):
        version = hashin.get_latest_version({'info': {'version': '0.3'}})
        self.assertEqual(version, '0.3')

    @mock.patch('hashin.urlopen')
    def test_get_hashes_error(self, murlopen):

        def mocked_get(url, **options):
            if url == "https://pypi.python.org/pypi/somepackage/json":
                return _Response({})
            raise NotImplementedError(url)

        murlopen.side_effect = mocked_get

        self.assertRaises(
            hashin.PackageError,
            hashin.run,
            'somepackage==1.2.3',
            'doesntmatter.txt',
            'sha256'
        )

    def test_amend_requirements_content_new(self):
        requirements = """
# empty so far
        """.strip() + '\n'
        new_lines = """
autocompeter==1.2.3 \\
    --hash=sha256:4d64ed1b9e0e73095f5cfa87f0e97ddb4c840049e8efeb7e63b46118ba1d623a
        """.strip() + '\n'
        result = hashin.amend_requirements_content(
            requirements, 'autocompeter', new_lines
        )
        self.assertEqual(result, requirements + new_lines)

    def test_amend_requirements_content_replacement(self):
        requirements = """
autocompeter==1.2.2
    --hash=sha256:33a5d0145e82326e781ddee1ad375f92cb84f8cfafea56e9504682adff64a5ee
        """.strip() + '\n'
        new_lines = """
autocompeter==1.2.3
    --hash=sha256:4d64ed1b9e0e73095f5cfa87f0e97ddb4c840049e8efeb7e63b46118ba1d623a
        """.strip() + '\n'
        result = hashin.amend_requirements_content(
            requirements, 'autocompeter', new_lines
        )
        self.assertEqual(result, new_lines)

    def test_amend_requirements_content_replacement_single_to_multi(self):
        """Change from autocompeter==1.2.2 to autocompeter==1.2.3
        when it was previously written as a single line and now
        ends up as a multi-line."""
        requirements = """
autocompeter==1.2.2 --hash=sha256:33a5d0145e82326e781ddee1ad375f92cb84f8cfafea56e9504682adff64a5ee
        """.strip() + '\n'
        new_lines = """
autocompeter==1.2.3
    --hash=sha256:4d64ed1b9e0e73095f5cfa87f0e97ddb4c840049e8efeb7e63b46118ba1d623a
        """.strip() + '\n'
        result = hashin.amend_requirements_content(
            requirements, 'autocompeter', new_lines
        )
        self.assertEqual(result, new_lines)

    def test_amend_requirements_content_replacement_2(self):
        requirements = """
autocompeter==1.2.2 \\
    --hash=sha256:01047449bc6e46792217fe62deba683979a60b33de7efd99ed564cf43907021b \\
    --hash=sha256:33a5d0145e82326e781ddee1ad375f92cb84f8cfafea56e9504682adff64a5ee
        """.strip() + '\n'
        new_lines = """
autocompeter==1.2.3 \\
    --hash=sha256:4d64ed1b9e0e73095f5cfa87f0e97ddb4c840049e8efeb7e63b46118ba1d623a
        """.strip() + '\n'
        result = hashin.amend_requirements_content(
            requirements, 'autocompeter', new_lines
        )
        self.assertEqual(result, new_lines)

    def test_amend_requirements_content_replacement_amonst_others(self):
        previous = """
otherpackage==1.0.0 --hash=sha256:cHay6ATFKumO3svU3B-8qBMYb-f1_dYlR4OgClWntEI
""".strip() + '\n'
        requirements = previous + """
autocompeter==1.2.2 \\
    --hash=sha256:01047449bc6e46792217fe62deba683979a60b33de7efd99ed564cf43907021b \\
    --hash=sha256:33a5d0145e82326e781ddee1ad375f92cb84f8cfafea56e9504682adff64a5ee
        """.strip() + '\n'
        new_lines = """
autocompeter==1.2.3 \\
    --hash=sha256:4d64ed1b9e0e73095f5cfa87f0e97ddb4c840049e8efeb7e63b46118ba1d623a
        """.strip()
        result = hashin.amend_requirements_content(
            requirements, 'autocompeter', new_lines
        )
        self.assertEqual(result, previous + new_lines)

    def test_amend_requirements_content_replacement_amonst_others_2(self):
        previous = (
            "https://github.com/rhelmer/pyinotify/archive/9ff352f.zip"
            "#egg=pyinotify "
            "--hash=sha256:2ae63cf475f0bd049b722fac20813d62aedc14957dd5a3bf00d120d2b5404460"
            "\n"
        )
        requirements = previous + """
autocompeter==1.2.2
    --hash=256:01047449bc6e46792217fe62deba683979a60b33de7efd99ed564cf43907021b \\
    --hash=256:33a5d0145e82326e781ddee1ad375f92cb84f8cfafea56e9504682adff64a5ee
        """.strip() + '\n'
        new_lines = """
autocompeter==1.2.3  \\
    --hash=256:4d64ed1b9e0e73095f5cfa87f0e97ddb4c840049e8efeb7e63b46118ba1d623a
        """.strip()
        result = hashin.amend_requirements_content(
            requirements, 'autocompeter', new_lines
        )
        self.assertEqual(result, previous + new_lines)

    @cleanup_tmpdir('hashin*')
    @mock.patch('hashin.urlopen')
    def test_run(self, murlopen):

        def mocked_get(url, **options):
            if url == "https://pypi.python.org/pypi/hashin/json":
                return _Response({
                    'info': {
                        'version': '0.10',
                    },
                    'releases': {
                        '0.10': [
                            {
                                'url': 'https://pypi.python.org/packages/2.7/p/hashin/hashin-0.10-py2-none-any.whl',
                            },
                            {
                                'url': 'https://pypi.python.org/packages/3.3/p/hashin/hashin-0.10-py3-none-any.whl',
                            },
                            {
                                'url': 'https://pypi.python.org/packages/source/p/hashin/hashin-0.10.tar.gz',
                            }
                        ]
                    }
                })
            elif url == "https://pypi.python.org/packages/2.7/p/hashin/hashin-0.10-py2-none-any.whl":
                return _Response(b"Some py2 wheel content\n")
            elif url == "https://pypi.python.org/packages/3.3/p/hashin/hashin-0.10-py3-none-any.whl":
                return _Response(b"Some py3 wheel content\n")
            elif url == "https://pypi.python.org/packages/source/p/hashin/hashin-0.10.tar.gz":
                return _Response(b"Some tarball content\n")

            raise NotImplementedError(url)

        murlopen.side_effect = mocked_get

        with tmpfile() as filename:
            with open(filename, 'w') as f:
                f.write('')

            my_stdout = StringIO()
            with redirect_stdout(my_stdout):
                retcode = hashin.run(
                    'hashin==0.10',
                    filename,
                    'sha256',
                    verbose=True
                )

            self.assertEqual(retcode, 0)
            with open(filename) as f:
                output = f.read()
            assert output.endswith('\n')
            lines = output.splitlines()

            self.assertEqual(
                lines[0],
                'hashin==0.10 \\'
            )
            self.assertEqual(
                lines[1],
                '    --hash=sha256:31104f8c0f9816a6d2135db4232cfa248b2c'
                '7525596263216577d3cdc93a3c25 \\'
            )
            self.assertEqual(
                lines[2],
                '    --hash=sha256:61fb59231ffe967ce693a2099cff59a2695e'
                '6d02acbb6b051033e3b1107d8008 \\'
            )
            self.assertEqual(
                lines[3],
                '    --hash=sha256:b2f06d3c4d148b648768abab5086afac0414'
                'e49eb4813e1f3c450b975c77cee9'
            )

            # Now check the verbose output
            out_lines = my_stdout.getvalue().splitlines()
            self.assertTrue(
                'https://pypi.python.org/pypi/hashin/json' in out_lines[0],
                out_lines[0]
            )
            # url to download
            self.assertTrue(
                'hashin-0.10-py2-none-any.whl' in out_lines[1],
                out_lines[1]
            )
            # file it got downloaded to
            self.assertTrue(
                'hashin-0.10-py2-none-any.whl' in out_lines[2],
                out_lines[2]
            )
            # hash it got
            self.assertTrue(
                '31104f8c0f9816a6d2135db4232cfa248b2c7525596263216577d3cdc'
                '93a3c25' in out_lines[3],
                out_lines[3]
            )

            # Change algorithm
            retcode = hashin.run('hashin==0.10', filename, 'sha512')
            self.assertEqual(retcode, 0)
            with open(filename) as f:
                output = f.read()
            assert output.endswith('\n')
            lines = output.splitlines()
            self.assertEqual(
                lines[0],
                'hashin==0.10 \\'
            )
            self.assertEqual(
                lines[1],
                '    --hash=sha512:45d1c5d2237a3b4f78b4198709fb2ecf1f781c823'
                '4ce3d94356f2100a36739433952c6c13b2843952f608949e6baa9f95055'
                'a314487cd8fb3f9d76522d8edb50 \\'
            )
            self.assertEqual(
                lines[2],
                '    --hash=sha512:0d63bf4c115154781846ecf573049324f06b021a1'
                'd4b92da4fae2bf491da2b83a13096b14d73e73cefad36855f4fa936bac4'
                'b2357dabf05a2b1e7329ff1e5455 \\'
            )
            self.assertEqual(
                lines[3],
                '    --hash=sha512:c32e6d9fb09dc36ab9222c4606a1f43a2dcc183a8'
                'c64bdd9199421ef779072c174fa044b155babb12860cf000e36bc4d3586'
                '94fa22420c997b1dd75b623d4daa'
            )

    def test_filter_releases(self):
        releases = [
            {
                'url': 'https://pypi.python.org/packages/2.7/p/hashin/hashin-0.10-py2-none-any.whl',
            },
            {
                'url': 'https://pypi.python.org/packages/3.3/p/hashin/hashin-0.10-py3-none-any.whl',
            },
            {
                'url': 'https://pypi.python.org/packages/source/p/hashin/hashin-0.10.tar.gz',
            },
        ]

        # With no filters, no releases are included
        self.assertEqual(hashin.filter_releases(releases, []), [])

        # With filters, other Python versions are filtered out.
        filtered = hashin.filter_releases(releases, ['py2'])
        self.assertEqual(filtered, [releases[0]])

        # Multiple filters work
        filtered = hashin.filter_releases(releases, ['py3', 'source'])
        self.assertEqual(filtered, [releases[1], releases[2]])

    def test_release_url_metadata_python(self):
        url = 'https://pypi.python.org/packages/3.4/P/Pygments/Pygments-2.1-py3-none-any.whl'
        self.assertEqual(hashin.release_url_metadata(url), {
            'package': 'Pygments',
            'version': '2.1',
            'python_version': 'py3',
            'abi': 'none',
            'platform': 'any',
            'format': 'whl',
        })
        url = 'https://pypi.python.org/packages/2.7/J/Jinja2/Jinja2-2.8-py2.py3-none-any.whl'
        self.assertEqual(hashin.release_url_metadata(url), {
            'package': 'Jinja2',
            'version': '2.8',
            'python_version': 'py2.py3',
            'abi': 'none',
            'platform': 'any',
            'format': 'whl',
        })
        url = 'https://pypi.python.org/packages/cp35/c/cffi/cffi-1.5.2-cp35-none-win32.whl'
        self.assertEqual(hashin.release_url_metadata(url), {
            'package': 'cffi',
            'version': '1.5.2',
            'python_version': 'cp35',
            'abi': 'none',
            'platform': 'win32',
            'format': 'whl',
        })
        url = ('https://pypi.python.org/packages/source/f/factory_boy/'
               'factory_boy-2.6.0.tar.gz#md5=d61ee02c6ac8d992f228c0346bd52f32')
        self.assertEqual(hashin.release_url_metadata(url), {
            'package': 'factory_boy',
            'version': '2.6.0',
            'python_version': 'source',
            'abi': None,
            'platform': None,
            'format': 'tar.gz',
        })
        url = ('https://pypi.python.org/packages/source/d/django-reversion/'
               'django-reversion-1.10.0.tar.gz')
        self.assertEqual(hashin.release_url_metadata(url), {
            'package': 'django-reversion',
            'version': '1.10.0',
            'python_version': 'source',
            'abi': None,
            'platform': None,
            'format': 'tar.gz',
        })
        url = 'https://pypi.python.org/packages/2.6/g/greenlet/greenlet-0.4.9-py2.6-win-amd64.egg'
        self.assertEqual(hashin.release_url_metadata(url), {
            'package': 'greenlet',
            'version': '0.4.9',
            'python_version': 'py2.6',
            'abi': None,
            'platform': 'win-amd64',
            'format': 'egg',
        })
        url = 'https://pypi.python.org/packages/2.4/p/pytz/pytz-2015.7-py2.4.egg'
        self.assertEqual(hashin.release_url_metadata(url), {
            'package': 'pytz',
            'version': '2015.7',
            'python_version': 'py2.4',
            'abi': None,
            'platform': None,
            'format': 'egg',
        })
        url = 'https://pypi.python.org/packages/2.7/g/gevent/gevent-1.1.0.win-amd64-py2.7.exe'
        self.assertEqual(hashin.release_url_metadata(url), {
            'package': 'gevent',
            'version': '1.1.0.win',
            'python_version': 'py2.7',
            'abi': None,
            'platform': 'amd64',
            'format': 'exe',
        })

    def test_expand_python_version(self):
        self.assertEqual(sorted(hashin.expand_python_version('2.7')),
                         ['2.7', 'cp27', 'py2', 'py2.7', 'py2.py3', 'source'])
        self.assertEqual(sorted(hashin.expand_python_version('3.5')),
                         ['3.5', 'cp35', 'py2.py3', 'py3', 'py3.5', 'source'])

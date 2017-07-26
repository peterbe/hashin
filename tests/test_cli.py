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

    def getcode(self):
        return self.status_code


class Tests(TestCase):

    # For when you use nosetests
    def shortDescription(self):
        return None

    @mock.patch('hashin.urlopen')
    def test_get_latest_version_simple(self, murlopen):
        version = hashin.get_latest_version({'info': {'version': '0.3'}})
        self.assertEqual(version, '0.3')

    @mock.patch('hashin.urlopen')
    def test_get_latest_version_non_pre_release(self, murlopen):
        version = hashin.get_latest_version({
            'info': {
                'version': '0.3',
            },
            'releases': {
                '0.99': {},
                '0.999': {},
                '1.1.0rc1': {},
                '1.1rc1': {},
                '1.0a1': {},
                '2.0b2': {},
                '2.0c3': {},
            }
        })
        self.assertEqual(version, '0.999')

    @mock.patch('hashin.urlopen')
    def test_get_latest_version_non_pre_release_leading_zeros(self, murlopen):
        version = hashin.get_latest_version({
            'info': {
                'version': '0.3',
            },
            'releases': {
                '0.04.13': {},
                '0.04.21': {},
                '0.04.09': {},
            }
        })
        self.assertEqual(version, '0.04.21')

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

    @mock.patch('hashin.urlopen')
    def test_non_200_ok_download(self, murlopen):

        def mocked_get(url, **options):
            return _Response({}, status_code=403)

        murlopen.side_effect = mocked_get

        self.assertRaises(
            hashin.PackageError,
            hashin.run,
            'somepackage==1.2.3',
            'doesntmatter.txt',
            'sha256'
        )

    @mock.patch('hashin.parser')
    @mock.patch('hashin.sys')
    @mock.patch('hashin.run')
    def test_main_packageerrors_stderr(self, mock_run, mock_sys, mock_parser):
        # Doesn't matter so much what, just make sure it breaks
        mock_run.side_effect = hashin.PackageError('Some message here')

        error = hashin.main()
        self.assertEqual(error, 1)
        mock_sys.stderr.write.assert_any_call('Some message here')
        mock_sys.stderr.write.assert_any_call('\n')

    @mock.patch('hashin.sys')
    def test_main_version(self, mock_sys):
        mock_sys.argv = [None, '--version']
        my_stdout = StringIO()
        with redirect_stdout(my_stdout):
            error = hashin.main()
        self.assertEqual(error, 0)
        version = my_stdout.getvalue().strip()
        import pkg_resources
        current_version = pkg_resources.get_distribution('hashin').version
        # No easy way to know what exact version it is
        self.assertEqual(version, current_version)

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

    def test_amend_requirements_content_new_similar_name(self):
        """This test came from https://github.com/peterbe/hashin/issues/15"""
        previous_1 = """
pytest-selenium==1.2.1 \
    --hash=sha256:e82f0a265b0e238ac42ac275d79313d0a7e0bef1a450633aeb3d6549cc14f517 \
    --hash=sha256:bd2121022ff3255ce82faec0ef3602462ec6bce9ca627b53462986cfc9b391e9
        """.strip() + '\n'
        previous_2 = """
selenium==2.52.0 \
    --hash=sha256:820550a740ca1f746c399a0101986c0e6f94fbfe3c6f976e3f694db452cbe124
        """.strip() + '\n'
        new_lines = """
selenium==2.53.1 \
    --hash=sha256:b1af142650ed7025f906349ae0d7ed1f1a1e635e6ce7ac67e2b2f854f9f8fdc1 \
    --hash=sha256:53929418a41295b526fbb68e43bc32fe93c3ef99c030b9e705caf1de486440de
        """.strip()
        result = hashin.amend_requirements_content(
            previous_1 + previous_2, 'selenium', new_lines
        )
        self.assertTrue(previous_1 in result)
        self.assertTrue(previous_2 not in result)
        self.assertTrue(new_lines in result)

    @cleanup_tmpdir('hashin*')
    @mock.patch('hashin.urlopen')
    def test_run(self, murlopen):

        def mocked_get(url, **options):
            if url == "https://pypi.python.org/pypi/hashin/json":
                return _Response({
                    'info': {
                        'version': '0.10',
                        'name': 'hashin',
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

    @cleanup_tmpdir('hashin*')
    @mock.patch('hashin.urlopen')
    def test_run_without_specific_version(self, murlopen):

        def mocked_get(url, **options):
            if url == 'https://pypi.python.org/pypi/hashin/json':
                return _Response({
                    'info': {
                        'version': '0.10',
                        'name': 'hashin',
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
            elif url == 'https://pypi.python.org/packages/2.7/p/hashin/hashin-0.10-py2-none-any.whl':
                return _Response(b'Some py2 wheel content\n')
            elif url == 'https://pypi.python.org/packages/3.3/p/hashin/hashin-0.10-py3-none-any.whl':
                return _Response(b'Some py3 wheel content\n')
            elif url == 'https://pypi.python.org/packages/source/p/hashin/hashin-0.10.tar.gz':
                return _Response(b'Some tarball content\n')

            raise NotImplementedError(url)

        murlopen.side_effect = mocked_get

        with tmpfile() as filename:
            with open(filename, 'w') as f:
                f.write('')

            my_stdout = StringIO()
            with redirect_stdout(my_stdout):
                retcode = hashin.run(
                    'hashin',
                    filename,
                    'sha256',
                    verbose=True
                )

            self.assertEqual(retcode, 0)
            with open(filename) as f:
                output = f.read()
            self.assertTrue(output.startswith('hashin==0.10'))

    @cleanup_tmpdir('hashin*')
    @mock.patch('hashin.urlopen')
    def test_run_contained_names(self, murlopen):
        """
        This is based on https://github.com/peterbe/hashin/issues/35
        which was a real bug discovered in hashin 0.8.0.
        It happens because the second package's name is entirely contained
        in the first package's name.
        """

        def mocked_get(url, **options):
            if url == "https://pypi.python.org/pypi/django-redis/json":
                return _Response({
                    'info': {
                        'version': '4.7.0',
                        'name': 'django-redis',
                    },
                    'releases': {
                        '4.7.0': [
                            {
                                'url': 'https://pypi.python.org/packages/source/p/django-redis/django-redis-4.7.0.tar.gz',
                            }
                        ]
                    }
                })
            elif url == "https://pypi.python.org/packages/source/p/django-redis/django-redis-4.7.0.tar.gz":
                return _Response(b"Some tarball content\n")
            elif url == "https://pypi.python.org/pypi/redis/json":
                return _Response({
                    'info': {
                        'version': '2.10.5',
                        'name': 'redis',
                    },
                    'releases': {
                        '2.10.5': [
                            {
                                'url': 'https://pypi.python.org/packages/source/p/redis/redis-2.10.5.tar.gz',
                            }
                        ]
                    }
                })
            elif url == "https://pypi.python.org/packages/source/p/redis/redis-2.10.5.tar.gz":
                return _Response(b"Some other tarball content\n")

            raise NotImplementedError(url)

        murlopen.side_effect = mocked_get

        with tmpfile() as filename:
            with open(filename, 'w') as f:
                f.write('')

            my_stdout = StringIO()
            with redirect_stdout(my_stdout):
                retcode = hashin.run(
                    'django-redis==4.7.0',
                    filename,
                    'sha256',
                    verbose=True
                )

            self.assertEqual(retcode, 0)
            with open(filename) as f:
                output = f.read()
            assert output.endswith('\n')
            lines = output.splitlines()
            self.assertTrue('django-redis==4.7.0 \\' in lines)
            self.assertEqual(len(lines), 2)

            # Now install the next package whose name is contained
            # in the first one.
            my_stdout = StringIO()
            with redirect_stdout(my_stdout):
                retcode = hashin.run(
                    'redis==2.10.5',
                    filename,
                    'sha256',
                    verbose=True
                )

            self.assertEqual(retcode, 0)
            with open(filename) as f:
                output = f.read()
            assert output.endswith('\n')
            lines = output.splitlines()
            self.assertTrue('django-redis==4.7.0 \\' in lines)
            self.assertTrue('redis==2.10.5 \\' in lines)
            self.assertEqual(len(lines), 4)

    @cleanup_tmpdir('hashin*')
    @mock.patch('hashin.urlopen')
    def test_run_case_insensitive(self, murlopen):
        """No matter how you run the cli with a package's case typing,
        it should find it and correct the cast typing per what it is
        inside the PyPI data."""

        def mocked_get(url, **options):
            if url == "https://pypi.python.org/pypi/HAShin/json":
                return _Response({
                    'info': {
                        'version': '0.10',
                        'name': 'hashin',
                    },
                    'releases': {
                        '0.10': [
                            {
                                'url': 'https://pypi.python.org/packages/source/p/hashin/hashin-0.10.tar.gz',
                            }
                        ]
                    }
                })
            elif url == "https://pypi.python.org/packages/source/p/hashin/hashin-0.10.tar.gz":
                return _Response(b"Some tarball content\n")
            elif url == "https://pypi.python.org/pypi/hashIN/json":
                return _Response({
                    'info': {
                        'version': '0.11',
                        'name': 'hashin',
                    },
                    'releases': {
                        '0.11': [
                            {
                                'url': 'https://pypi.python.org/packages/source/p/hashin/hashin-0.11.tar.gz',
                            }
                        ]
                    }
                })
            elif url == "https://pypi.python.org/packages/source/p/hashin/hashin-0.11.tar.gz":
                return _Response(b"Some different tarball content\n")

            raise NotImplementedError(url)

        murlopen.side_effect = mocked_get

        with tmpfile() as filename:
            with open(filename, 'w') as f:
                f.write('')

            my_stdout = StringIO()
            with redirect_stdout(my_stdout):
                retcode = hashin.run(
                    'HAShin==0.10',
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

            # Change version
            retcode = hashin.run('hashIN==0.11', filename, 'sha256')
            self.assertEqual(retcode, 0)
            with open(filename) as f:
                output = f.read()
            assert output.endswith('\n')
            lines = output.splitlines()
            self.assertEqual(
                lines[0],
                'hashin==0.11 \\'
            )

    @cleanup_tmpdir('hashin*')
    @mock.patch('hashin.urlopen')
    def test_run_pep_0496(self, murlopen):
        """
        Properly pass through specifiers which look like:

           enum==1.1.6; python_version <= '3.4'

        These can include many things besides python_version; see
        https://www.python.org/dev/peps/pep-0496/
        """

        def mocked_get(url, **options):
            if url == "https://pypi.python.org/pypi/enum34/json":
                return _Response({
                    'info': {
                        'version': '1.1.6',
                        'name': 'enum34',
                    },
                    'releases': {
                        "1.1.6": [

                            {
                                "has_sig": False,
                                "upload_time": "2016-05-16T03:31:13",
                                "comment_text": "",
                                "python_version": "py2",
                                "url": "https://pypi.python.org/packages/c5/db/enum34-1.1.6-py2-none-any.whl",
                                "md5_digest": "68f6982cc07dde78f4b500db829860bd",
                                "downloads": 4297423,
                                "filename": "enum34-1.1.6-py2-none-any.whl",
                                "packagetype": "bdist_wheel",
                                "path": "c5/db/enum34-1.1.6-py2-none-any.whl",
                                "size": 12427
                            },
                            {
                                "has_sig": False,
                                "upload_time": "2016-05-16T03:31:19",
                                "comment_text": "",
                                "python_version": "py3",
                                "url": "https://pypi.python.org/packages/af/42/enum34-1.1.6-py3-none-any.whl",
                                "md5_digest": "a63ecb4f0b1b85fb69be64bdea999b43",
                                "downloads": 98598,
                                "filename": "enum34-1.1.6-py3-none-any.whl",
                                "packagetype": "bdist_wheel",
                                "path": "af/42/enum34-1.1.6-py3-none-any.whl",
                                "size": 12428
                            },
                            {
                                "has_sig": False,
                                "upload_time": "2016-05-16T03:31:30",
                                "comment_text": "",
                                "python_version": "source",
                                "url": "https://pypi.python.org/packages/bf/3e/enum34-1.1.6.tar.gz",
                                "md5_digest": "5f13a0841a61f7fc295c514490d120d0",
                                "downloads": 188090,
                                "filename": "enum34-1.1.6.tar.gz",
                                "packagetype": "sdist",
                                "path": "bf/3e/enum34-1.1.6.tar.gz",
                                "size": 40048
                            },
                            {
                                "has_sig": False,
                                "upload_time": "2016-05-16T03:31:48",
                                "comment_text": "",
                                "python_version": "source",
                                "url": "https://pypi.python.org/packages/e8/26/enum34-1.1.6.zip",
                                "md5_digest": "61ad7871532d4ce2d77fac2579237a9e",
                                "downloads": 775920,
                                "filename": "enum34-1.1.6.zip",
                                "packagetype": "sdist",
                                "path": "e8/26/enum34-1.1.6.zip",
                                "size": 44773
                            }
                        ]
                    }
                })
            elif url.startswith("https://pypi.python.org/packages"):
                return _Response(b"Some tarball content\n")

            raise NotImplementedError(url)

        murlopen.side_effect = mocked_get

        with tmpfile() as filename:
            with open(filename, 'w') as f:
                f.write('')

            my_stdout = StringIO()
            with redirect_stdout(my_stdout):
                retcode = hashin.run(
                    "enum34==1.1.6; python_version <= '3.4'",
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
                "enum34==1.1.6; python_version <= '3.4' \\"
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
        url = 'https://pypi.python.org/packages/d5/0d/445186a82bbcc75166a507eff586df683c73641e7d6bb7424a44426dca71/Django-1.8.12-py2.py3-none-any.whl'
        self.assertEqual(hashin.release_url_metadata(url), {
            'package': 'Django',
            'version': '1.8.12',
            'python_version': 'py2.py3',
            'abi': 'none',
            'platform': 'any',
            'format': 'whl',
        })
        # issue 32
        url = 'https://pypi.python.org/packages/a4/ae/65500d0becffe3dd6671fbdc6010cc0c4a8b715dbd94315ba109bbc54bc5/turbine-0.0.3.linux-x86_64.tar.gz'
        self.assertEqual(hashin.release_url_metadata(url), {
            'package': 'turbine',
            'version': '0.0.3.linux',
            'python_version': 'source',
            'abi': None,
            'platform': 'x86_64',
            'format': 'tar.gz',
        })

    def test_expand_python_version(self):
        self.assertEqual(sorted(hashin.expand_python_version('2.7')),
                         ['2.7', 'cp27', 'py2', 'py2.7', 'py2.py3', 'source'])
        self.assertEqual(sorted(hashin.expand_python_version('3.5')),
                         ['3.5', 'cp35', 'py2.py3', 'py3', 'py3.5', 'source'])

    @cleanup_tmpdir('hashin*')
    @mock.patch('hashin.urlopen')
    def test_get_package_hashes(self, murlopen):

        def mocked_get(url, **options):
            if url == "https://pypi.python.org/pypi/hashin/json":
                return _Response({
                    'info': {
                        'version': '0.10',
                        'name': 'hashin',
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

        result = hashin.get_package_hashes(
            package='hashin',
            version='0.10',
            algorithm='sha512',
        )

        expected = {
            'package': 'hashin',
            'version': '0.10',
            'hashes': [
                {
                    'url': 'https://pypi.python.org/packages/2.7/p/hashin/hashin-0.10-py2-none-any.whl',
                    'hash': '45d1c5d2237a3b4f78b4198709fb2ecf1f781c8234ce3d94356f2100a36739433952c6c13b2843952f608949e6baa9f95055a314487cd8fb3f9d76522d8edb50'
                },
                {
                    'url': 'https://pypi.python.org/packages/3.3/p/hashin/hashin-0.10-py3-none-any.whl',
                    'hash': '0d63bf4c115154781846ecf573049324f06b021a1d4b92da4fae2bf491da2b83a13096b14d73e73cefad36855f4fa936bac4b2357dabf05a2b1e7329ff1e5455'
                },
                {
                    'url': 'https://pypi.python.org/packages/source/p/hashin/hashin-0.10.tar.gz',
                    'hash': 'c32e6d9fb09dc36ab9222c4606a1f43a2dcc183a8c64bdd9199421ef779072c174fa044b155babb12860cf000e36bc4d358694fa22420c997b1dd75b623d4daa'
                }
            ]
        }

        self.assertEqual(result, expected)

    @cleanup_tmpdir('hashin*')
    @mock.patch('hashin.urlopen')
    def test_get_package_hashes_without_version(self, murlopen):

        def mocked_get(url, **options):
            if url == 'https://pypi.python.org/pypi/hashin/json':
                return _Response({
                    'info': {
                        'version': '0.10',
                        'name': 'hashin',
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
            elif url == 'https://pypi.python.org/packages/2.7/p/hashin/hashin-0.10-py2-none-any.whl':
                return _Response(b'Some py2 wheel content\n')
            elif url == 'https://pypi.python.org/packages/3.3/p/hashin/hashin-0.10-py3-none-any.whl':
                return _Response(b'Some py3 wheel content\n')
            elif url == 'https://pypi.python.org/packages/source/p/hashin/hashin-0.10.tar.gz':
                return _Response(b'Some tarball content\n')

            elif url == 'https://pypi.python.org/pypi/uggamugga/json':
                return _Response({
                    'info': {
                        'version': '1.2.3',
                        'name': 'uggamugga',
                    },
                    'releases': {}  # Note!
                })

            raise NotImplementedError(url)

        murlopen.side_effect = mocked_get

        stdout_buffer = StringIO()
        with redirect_stdout(stdout_buffer):
            result = hashin.get_package_hashes(
                package='hashin',
                verbose=True,
                # python_versions=('3.5',),
            )
        self.assertEqual(result['package'], 'hashin')
        self.assertEqual(result['version'], '0.10')
        self.assertTrue(result['hashes'])
        stdout = stdout_buffer.getvalue()
        self.assertTrue('Latest version for hashin is 0.10' in stdout)

        # Let's do it again and mess with a few things.
        # First specify python_versions.
        stdout_buffer = StringIO()
        with redirect_stdout(stdout_buffer):
            result = hashin.get_package_hashes(
                package='hashin',
                verbose=True,
                python_versions=('3.5',),
            )
        self.assertEqual(len(result['hashes']), 2)  # instead of 3
        # Specify an unrecognized python version
        self.assertRaises(
            hashin.PackageError,
            hashin.get_package_hashes,
            package='hashin',
            python_versions=('2.99999',),
        )

        # Look for a package without any releases
        self.assertRaises(
            hashin.PackageError,
            hashin.get_package_hashes,
            package='uggamugga',
        )

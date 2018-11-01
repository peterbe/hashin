# -*- coding: utf-8 -*-

import argparse
import sys
import json

import pytest
import mock
from packaging.requirements import Requirement

import hashin


if sys.version_info >= (3,):
    # As in, Python 3
    from urllib.error import HTTPError

else:
    FileNotFoundError = IOError  # ugly but necessary
    # Python 2 does not have this exception.
    HTTPError = None


class _Response(object):
    def __init__(self, content, status_code=200, headers=None):
        if isinstance(content, dict):
            content = json.dumps(content).encode("utf-8")
        self.content = content
        self.status_code = status_code
        if headers is None:
            headers = {"Content-Type": "text/html"}
        self.headers = headers

    def read(self):
        return self.content

    def getcode(self):
        return self.status_code


def test_get_latest_version_simple(murlopen):
    version = hashin.get_latest_version({"info": {"version": "0.3"}}, False)
    assert version == "0.3"

    @mock.patch("hashin.urlopen")
    def test_get_latest_version_non_pre_release(self, murlopen):
        version = hashin.get_latest_version(
            {
                "info": {"version": "0.3"},
                "releases": {
                    "0.99": {},
                    "0.999": {},
                    "1.1.0rc1": {},
                    "1.1rc1": {},
                    "1.0a1": {},
                    "2.0b2": {},
                    "2.0c3": {},
                },
            },
            False,
        )
        assert version == "0.999"


def test_get_latest_version_only_pre_release(murlopen):
    with pytest.raises(hashin.NoVersionsError) as exc_info:
        hashin.get_latest_version(
            {
                "info": {"version": "0.3"},
                "releases": {
                    "1.1.0rc1": {},
                    "1.1rc1": {},
                    "1.0a1": {},
                    "2.0b2": {},
                    "2.0c3": {},
                },
            },
            False,
        )
    assert str(exc_info.value) == (
        "No valid version found. But, found 5 pre-releases. "
        "Consider running again with the --include-prereleases flag."
    )

    version = hashin.get_latest_version(
        {
            "info": {"version": "0.3"},
            "releases": {
                "1.1.0rc1": {},
                "1.1rc1": {},
                "1.0a1": {},
                "2.0b2": {},
                "2.0c3": {},
            },
        },
        True,
    )
    assert version == "2.0c3"


def test_get_latest_version_non_pre_release_leading_zeros(murlopen):
    version = hashin.get_latest_version(
        {
            "info": {"version": "0.3"},
            "releases": {"0.04.13": {}, "0.04.21": {}, "0.04.09": {}},
        },
        False,
    )
    assert version == "0.04.21"


def test_get_hashes_error(murlopen):
    def mocked_get(url, **options):
        if url == "https://pypi.org/pypi/somepackage/json":
            return _Response({})
        raise NotImplementedError(url)

    murlopen.side_effect = mocked_get
    with pytest.raises(hashin.PackageError):
        hashin.run("somepackage==1.2.3", "doesntmatter.txt", "sha256")


def test_non_200_ok_download(murlopen):
    def mocked_get(url, **options):
        return _Response({}, status_code=403)

    murlopen.side_effect = mocked_get

    with pytest.raises(hashin.PackageError):
        hashin.run("somepackage==1.2.3", "doesntmatter.txt", "sha256")


def test_main_packageerrors_stderr(mock_run, capsys, mock_get_parser):
    # Doesn't matter so much what, just make sure it breaks
    mock_run.side_effect = hashin.PackageError("Some message here")

    def mock_parse_args(*a, **k):
        return argparse.Namespace(
            packages=["something"],
            requirements_file="requirements.txt",
            algorithm="sha256",
            python_version="3.8",
            verbose=False,
            include_prereleases=False,
            dry_run=False,
            update_all=False,
            interactive=False,
        )

    mock_get_parser().parse_args.side_effect = mock_parse_args

    error = hashin.main()
    assert error == 1
    captured = capsys.readouterr()
    assert captured.err == "Some message here\n"


def test_packages_and_update_all(capsys, mock_get_parser):
    def mock_parse_args(*a, **k):
        return argparse.Namespace(
            packages=["something"],
            requirements_file="requirements.txt",
            algorithm="sha256",
            python_version="3.8",
            verbose=False,
            include_prereleases=False,
            dry_run=False,
            update_all=True,  # Note!
            interactive=False,
        )

    mock_get_parser().parse_args.side_effect = mock_parse_args

    error = hashin.main()
    assert error == 2
    captured = capsys.readouterr()
    assert captured.err == (
        "Can not combine the --update-all option with a list of packages.\n"
    )


def test_no_packages_and_not_update_all(capsys, mock_get_parser):
    def mock_parse_args(*a, **k):
        return argparse.Namespace(
            packages=[],  # Note!
            requirements_file="requirements.txt",
            algorithm="sha256",
            python_version="3.8",
            verbose=False,
            include_prereleases=False,
            dry_run=False,
            update_all=False,
            interactive=False,
        )

    mock_get_parser().parse_args.side_effect = mock_parse_args

    error = hashin.main()
    assert error == 3
    captured = capsys.readouterr()
    assert captured.err == ("If you don't use --update-all you must list packages.\n")


def test_interactive_not_update_all(mock_get_parser, capsys):
    def mock_parse_args(*a, **k):
        return argparse.Namespace(
            packages=[],
            requirements_file="requirements.txt",
            algorithm="sha256",
            python_version="3.8",
            verbose=False,
            include_prereleases=False,
            dry_run=False,
            update_all=False,  # Note!
            interactive=True,  # Note!
        )

    mock_get_parser().parse_args.side_effect = mock_parse_args

    error = hashin.main()
    assert error == 4
    captured = capsys.readouterr()
    assert not captured.out
    assert captured.err == (
        "--interactive (or -i) is only applicable together with --update-all (or -u).\n"
    )


def test_main_version(mock_sys, capsys):
    mock_sys.argv = [None, "--version"]
    error = hashin.main()
    assert error == 0
    captured = capsys.readouterr()
    version = captured.out.strip()
    import pkg_resources

    current_version = pkg_resources.get_distribution("hashin").version
    # No easy way to know what exact version it is
    assert version == current_version


def test_amend_requirements_content_new():
    requirements = (
        """
# empty so far
    """.strip()
        + "\n"
    )
    new_lines = (
        "autocompeter",
        """
autocompeter==1.2.3 \\
    --hash=sha256:4d64ed1b9e0e73095f5cfa87f0e97ddb4c840049e8efeb7e63b46118ba1d623a
    """.strip()
        + "\n",
    )
    result = hashin.amend_requirements_content(requirements, [new_lines])
    assert result == requirements + new_lines[1]


def test_amend_requirements_content_multiple_merge():
    requirements = (
        """
autocompeter==1.2.3 \\
    --hash=sha256:4d64ed1b9e0e73095f5cfa87f0e97ddb4c840049e8efeb7e63b46118ba1d623a
otherpackage==1.0.0 \\
    --hash=sha256:cHay6ATFKumO3svU3B-8qBMYb-f1_dYlR4OgClWntEI
# Comment here
examplepackage==9.8.6 \\
    --hash=sha256:33a5d0145e82326e781ddee1ad375f92cb84f8cfafea56e9504682adff64a5ee
    """.strip()
        + "\n"
    )

    all_new_lines = []
    all_new_lines.append(
        (
            "autocompeter",
            """
autocompeter==1.3.0 \\
    --hash=sha256:53929418a41295b526fbb68e43bc32fe93c3ef99c030b9e705caf1de486440de
    """.strip()
            + "\n",
        )
    )
    all_new_lines.append(
        (
            "examplepackage",
            """
examplepackage==10.0.0 \\
    --hash=sha256:fd54e979d3747be638f59de44a7f6523bed56d81961a438462b1346f49be5fe4
    --hash=sha256:12ce5c2ef718e7e31cef2e2a3bde771d9216f2cb014efba963e69cb709bcbbd1
    """.strip()
            + "\n",
        )
    )

    result = hashin.amend_requirements_content(requirements, all_new_lines)
    expect = (
        """
autocompeter==1.3.0 \\
    --hash=sha256:53929418a41295b526fbb68e43bc32fe93c3ef99c030b9e705caf1de486440de
otherpackage==1.0.0 \\
    --hash=sha256:cHay6ATFKumO3svU3B-8qBMYb-f1_dYlR4OgClWntEI
# Comment here
examplepackage==10.0.0 \\
    --hash=sha256:fd54e979d3747be638f59de44a7f6523bed56d81961a438462b1346f49be5fe4
    --hash=sha256:12ce5c2ef718e7e31cef2e2a3bde771d9216f2cb014efba963e69cb709bcbbd1
    """.strip()
        + "\n"
    )
    assert result == expect


def test_amend_requirements_content_replacement():
    requirements = (
        """
autocompeter==1.2.2
    --hash=sha256:33a5d0145e82326e781ddee1ad375f92cb84f8cfafea56e9504682adff64a5ee
    """.strip()
        + "\n"
    )

    new_lines = (
        "autocompeter",
        """
autocompeter==1.2.3
    --hash=sha256:4d64ed1b9e0e73095f5cfa87f0e97ddb4c840049e8efeb7e63b46118ba1d623a
    """.strip()
        + "\n",
    )

    result = hashin.amend_requirements_content(requirements, [new_lines])
    assert result == new_lines[1]


def test_amend_requirements_content_actually_not_replacement():
    requirements = (
        """
autocompeter==1.2.2
    --hash=sha256:33a5d0145e82326e781ddee1ad375f92cb84f8cfafea56e9504682adff64a5ee
    --hash=sha256:4d64ed1b9e0e73095f5cfa87f0e97ddb4c840049e8efeb7e63b46118ba1d623a
    """.strip()
        + "\n"
    )

    new_lines = (
        "autocompeter",
        """
autocompeter==1.2.2
    --hash=sha256:4d64ed1b9e0e73095f5cfa87f0e97ddb4c840049e8efeb7e63b46118ba1d623a
    --hash=sha256:33a5d0145e82326e781ddee1ad375f92cb84f8cfafea56e9504682adff64a5ee
    """.strip()
        + "\n",
    )

    result = hashin.amend_requirements_content(requirements, [new_lines])
    # It should be unchanged because the only thing that changed was the
    # order of the --hash lines.
    assert result == requirements


def test_amend_requirements_content_replacement_addition():
    requirements = (
        """
autocompeter==1.2.2
    --hash=sha256:33a5d0145e82326e781ddee1ad375f92cb84f8cfafea56e9504682adff64a5ee
    """.strip()
        + "\n"
    )

    new_lines = (
        "autocompeter",
        """
autocompeter==1.2.2
    --hash=sha256:4d64ed1b9e0e73095f5cfa87f0e97ddb4c840049e8efeb7e63b46118ba1d623a
    --hash=sha256:33a5d0145e82326e781ddee1ad375f92cb84f8cfafea56e9504682adff64a5ee
    """.strip()
        + "\n",
    )

    result = hashin.amend_requirements_content(requirements, [new_lines])
    assert result == new_lines[1]


def test_amend_requirements_content_replacement_single_to_multi():
    """Change from autocompeter==1.2.2 to autocompeter==1.2.3
    when it was previously written as a single line and now
    ends up as a multi-line."""
    requirements = (
        """
autocompeter==1.2.2 --hash=sha256:33a5d0145e82326e781ddee1ad375f92cb84f8cfafea56e9504682adff64a5ee
    """.strip()
        + "\n"
    )
    new_lines = (
        "autocompeter",
        """
autocompeter==1.2.3
    --hash=sha256:4d64ed1b9e0e73095f5cfa87f0e97ddb4c840049e8efeb7e63b46118ba1d623a
    """.strip()
        + "\n",
    )
    result = hashin.amend_requirements_content(requirements, [new_lines])
    assert result == new_lines[1]


def test_amend_requirements_content_replacement_2():
    requirements = (
        """
autocompeter==1.2.2 \\
    --hash=sha256:01047449bc6e46792217fe62deba683979a60b33de7efd99ed564cf43907021b \\
    --hash=sha256:33a5d0145e82326e781ddee1ad375f92cb84f8cfafea56e9504682adff64a5ee
    """.strip()
        + "\n"
    )
    new_lines = (
        "autocompeter",
        """
autocompeter==1.2.3 \\
    --hash=sha256:4d64ed1b9e0e73095f5cfa87f0e97ddb4c840049e8efeb7e63b46118ba1d623a
    """.strip()
        + "\n",
    )
    result = hashin.amend_requirements_content(requirements, [new_lines])
    assert result == new_lines[1]


def test_amend_requirements_content_replacement_amonst_others():
    previous = (
        """
otherpackage==1.0.0 --hash=sha256:cHay6ATFKumO3svU3B-8qBMYb-f1_dYlR4OgClWntEI
""".strip()
        + "\n"
    )
    requirements = (
        previous
        + """
autocompeter==1.2.2 \\
    --hash=sha256:01047449bc6e46792217fe62deba683979a60b33de7efd99ed564cf43907021b \\
    --hash=sha256:33a5d0145e82326e781ddee1ad375f92cb84f8cfafea56e9504682adff64a5ee
    """.strip()
        + "\n"
    )
    new_lines = (
        "autocompeter",
        """
autocompeter==1.2.3 \\
    --hash=sha256:4d64ed1b9e0e73095f5cfa87f0e97ddb4c840049e8efeb7e63b46118ba1d623a
    """.strip(),
    )
    result = hashin.amend_requirements_content(requirements, [new_lines])
    assert result == previous + new_lines[1]


def test_amend_requirements_content_replacement_amonst_others_2():
    previous = (
        "https://github.com/rhelmer/pyinotify/archive/9ff352f.zip"
        "#egg=pyinotify "
        "--hash=sha256:2ae63cf475f0bd049b722fac20813d62aedc14957dd5a3bf00d120d2b5404460"
        "\n"
    )
    requirements = (
        previous
        + """
autocompeter==1.2.2
    --hash=256:01047449bc6e46792217fe62deba683979a60b33de7efd99ed564cf43907021b \\
    --hash=256:33a5d0145e82326e781ddee1ad375f92cb84f8cfafea56e9504682adff64a5ee
    """.strip()
        + "\n"
    )
    new_lines = (
        "autocompeter",
        """
autocompeter==1.2.3  \\
    --hash=256:4d64ed1b9e0e73095f5cfa87f0e97ddb4c840049e8efeb7e63b46118ba1d623a
        """.strip(),
    )
    result = hashin.amend_requirements_content(requirements, [new_lines])
    assert result == previous + new_lines[1]


def test_amend_requirements_content_new_similar_name():
    """This test came from https://github.com/peterbe/hashin/issues/15"""
    previous_1 = (
        """
pytest-selenium==1.2.1 \
    --hash=sha256:e82f0a265b0e238ac42ac275d79313d0a7e0bef1a450633aeb3d6549cc14f517 \
    --hash=sha256:bd2121022ff3255ce82faec0ef3602462ec6bce9ca627b53462986cfc9b391e9
    """.strip()
        + "\n"
    )
    previous_2 = (
        """
selenium==2.52.0 \
    --hash=sha256:820550a740ca1f746c399a0101986c0e6f94fbfe3c6f976e3f694db452cbe124
    """.strip()
        + "\n"
    )
    new_lines = (
        "selenium",
        """
selenium==2.53.1 \
    --hash=sha256:b1af142650ed7025f906349ae0d7ed1f1a1e635e6ce7ac67e2b2f854f9f8fdc1 \
    --hash=sha256:53929418a41295b526fbb68e43bc32fe93c3ef99c030b9e705caf1de486440de
        """.strip(),
    )
    result = hashin.amend_requirements_content(previous_1 + previous_2, [new_lines])
    assert previous_1 in result
    assert previous_2 not in result
    assert new_lines[1] in result


def test_run(murlopen, tmpfile, capsys):
    def mocked_get(url, **options):
        if url == "https://pypi.org/pypi/hashin/json":
            return _Response(
                {
                    "info": {"version": "0.10", "name": "hashin"},
                    "releases": {
                        "0.10": [
                            {
                                "url": "https://pypi.org/packages/2.7/p/hashin/hashin-0.10-py2-none-any.whl",
                                "digests": {"sha256": "aaaaa"},
                            },
                            {
                                "url": "https://pypi.org/packages/3.3/p/hashin/hashin-0.10-py3-none-any.whl",
                                "digests": {"sha256": "bbbbb"},
                            },
                            {
                                "url": "https://pypi.org/packages/source/p/hashin/hashin-0.10.tar.gz",
                                "digests": {"sha256": "ccccc"},
                            },
                        ]
                    },
                }
            )
        elif (
            url == "https://pypi.org/packages/2.7/p/hashin/hashin-0.10-py2-none-any.whl"
        ):
            return _Response(b"Some py2 wheel content\n")
        elif (
            url == "https://pypi.org/packages/3.3/p/hashin/hashin-0.10-py3-none-any.whl"
        ):
            return _Response(b"Some py3 wheel content\n")
        elif url == "https://pypi.org/packages/source/p/hashin/hashin-0.10.tar.gz":
            return _Response(b"Some tarball content\n")

        raise NotImplementedError(url)

    murlopen.side_effect = mocked_get

    with tmpfile() as filename:
        with open(filename, "w") as f:
            f.write("")

        retcode = hashin.run("hashin==0.10", filename, "sha256", verbose=True)

        assert retcode == 0
        with open(filename) as f:
            output = f.read()
        assert output
        assert output.endswith("\n")
        lines = output.splitlines()

        assert lines[0] == "hashin==0.10 \\"
        assert lines[1] == "    --hash=sha256:aaaaa \\"
        assert lines[2] == "    --hash=sha256:bbbbb \\"
        assert lines[3] == "    --hash=sha256:ccccc"

        # Now check the verbose output
        captured = capsys.readouterr()
        out_lines = captured.out.splitlines()
        # out_lines = my_stdout.getvalue().splitlines()
        assert "https://pypi.org/pypi/hashin/json" in out_lines[0], out_lines[0]
        # url to download
        assert "hashin-0.10-py2-none-any.whl" in out_lines[1], out_lines[1]

        assert (
            "Found hash for https://pypi.org/packages/2.7/p/hashin/hashin-0.10-py2-none-any.whl"
            in out_lines[1]
        ), out_lines[1]

        # hash it got
        assert "aaaaa" in out_lines[2], out_lines[2]

        # Change algorithm
        retcode = hashin.run("hashin==0.10", filename, "sha512")
        assert retcode == 0
        with open(filename) as f:
            output = f.read()
        assert output.endswith("\n")
        lines = output.splitlines()
        assert lines[0] == "hashin==0.10 \\"
        assert (
            "    --hash=sha512:0d63bf4c115154781846ecf573049324f06b021a1"
            "d4b92da4fae2bf491da2b83a13096b14d73e73cefad36855f4fa936bac4"
            "b2357dabf05a2b1e7329ff1e5455 \\"
        ) in lines
        assert (
            "    --hash=sha512:45d1c5d2237a3b4f78b4198709fb2ecf1f781c823"
            "4ce3d94356f2100a36739433952c6c13b2843952f608949e6baa9f95055"
            "a314487cd8fb3f9d76522d8edb50 \\"
        ) in lines
        assert (
            "    --hash=sha512:c32e6d9fb09dc36ab9222c4606a1f43a2dcc183a8"
            "c64bdd9199421ef779072c174fa044b155babb12860cf000e36bc4d3586"
            "94fa22420c997b1dd75b623d4daa"
        ) in lines


def test_run_atomic_not_write_with_error_on_last_package(murlopen, tmpfile):
    def mocked_get(url, **options):

        if url == "https://pypi.org/pypi/hashin/json":
            return _Response(
                {
                    "info": {"version": "0.10", "name": "hashin"},
                    "releases": {
                        "0.10": [
                            {
                                "url": "https://pypi.org/packages/2.7/p/hashin/hashin-0.10-py2-none-any.whl",
                                "digests": {"sha256": "aaaaa"},
                            },
                            {
                                "url": "https://pypi.org/packages/3.3/p/hashin/hashin-0.10-py3-none-any.whl",
                                "digests": {"sha256": "bbbbb"},
                            },
                            {
                                "url": "https://pypi.org/packages/source/p/hashin/hashin-0.10.tar.gz",
                                "digests": {"sha256": "ccccc"},
                            },
                        ]
                    },
                }
            )

        if url == "https://pypi.org/pypi/gobblygook/json":
            if HTTPError:
                raise HTTPError(url, 404, "Page not found", {}, None)
            else:
                return _Response({}, status_code=404)

        raise NotImplementedError(url)

    murlopen.side_effect = mocked_get

    with tmpfile() as filename:
        with open(filename, "w") as f:
            f.write("")

        with pytest.raises(hashin.PackageNotFoundError):
            hashin.run(["hashin", "gobblygook"], filename, "sha256", verbose=True)

        with open(filename) as f:
            output = f.read()
            # Crucial that nothing was written to the file.
            # The first package would find some new requirements but the second
            # package should cancel the write.
            assert output == ""


def test_run_interactive(murlopen, tmpfile, capsys):
    def mocked_get(url, **options):

        if url == "https://pypi.org/pypi/hashin/json":
            return _Response(
                {
                    "info": {"version": "0.10", "name": "hashin"},
                    "releases": {
                        "0.10": [
                            {
                                "url": "https://pypi.org/packages/2.7/p/hashin/hashin-0.10-py2-none-any.whl",
                                "digests": {"sha256": "aaaaa"},
                            },
                            {
                                "url": "https://pypi.org/packages/3.3/p/hashin/hashin-0.10-py3-none-any.whl",
                                "digests": {"sha256": "bbbbb"},
                            },
                            {
                                "url": "https://pypi.org/packages/source/p/hashin/hashin-0.10.tar.gz",
                                "digests": {"sha256": "ccccc"},
                            },
                        ]
                    },
                }
            )
        elif url == "https://pypi.org/pypi/requests/json":
            return _Response(
                {
                    "info": {"version": "1.2.4", "name": "requests"},
                    "releases": {
                        "1.2.4": [
                            {
                                "url": "https://pypi.org/packages/source/p/requests/requests-1.2.4.tar.gz",
                                "digests": {"sha256": "dededede"},
                            }
                        ]
                    },
                }
            )
        if url == "https://pypi.org/pypi/enum34/json":
            return _Response(
                {
                    "info": {"version": "1.1.6", "name": "enum34"},
                    "releases": {
                        "1.1.6": [
                            {
                                "has_sig": False,
                                "upload_time": "2016-05-16T03:31:13",
                                "comment_text": "",
                                "python_version": "py2",
                                "url": "https://pypi.org/packages/c5/db/enum34-1.1.6-py2-none-any.whl",
                                "digests": {
                                    "md5": "68f6982cc07dde78f4b500db829860bd",
                                    "sha256": "aaaaa",
                                },
                                "md5_digest": "68f6982cc07dde78f4b500db829860bd",
                                "downloads": 4297423,
                                "filename": "enum34-1.1.6-py2-none-any.whl",
                                "packagetype": "bdist_wheel",
                                "path": "c5/db/enum34-1.1.6-py2-none-any.whl",
                                "size": 12427,
                            },
                            {
                                "has_sig": False,
                                "upload_time": "2016-05-16T03:31:19",
                                "comment_text": "",
                                "python_version": "py3",
                                "url": "https://pypi.org/packages/af/42/enum34-1.1.6-py3-none-any.whl",
                                "md5_digest": "a63ecb4f0b1b85fb69be64bdea999b43",
                                "digests": {
                                    "md5": "a63ecb4f0b1b85fb69be64bdea999b43",
                                    "sha256": "bbbbb",
                                },
                                "downloads": 98598,
                                "filename": "enum34-1.1.6-py3-none-any.whl",
                                "packagetype": "bdist_wheel",
                                "path": "af/42/enum34-1.1.6-py3-none-any.whl",
                                "size": 12428,
                            },
                            {
                                "has_sig": False,
                                "upload_time": "2016-05-16T03:31:30",
                                "comment_text": "",
                                "python_version": "source",
                                "url": "https://pypi.org/packages/bf/3e/enum34-1.1.6.tar.gz",
                                "md5_digest": "5f13a0841a61f7fc295c514490d120d0",
                                "digests": {
                                    "md5": "5f13a0841a61f7fc295c514490d120d0",
                                    "sha256": "ccccc",
                                },
                                "downloads": 188090,
                                "filename": "enum34-1.1.6.tar.gz",
                                "packagetype": "sdist",
                                "path": "bf/3e/enum34-1.1.6.tar.gz",
                                "size": 40048,
                            },
                            {
                                "has_sig": False,
                                "upload_time": "2016-05-16T03:31:48",
                                "comment_text": "",
                                "python_version": "source",
                                "url": "https://pypi.org/packages/e8/26/enum34-1.1.6.zip",
                                "md5_digest": "61ad7871532d4ce2d77fac2579237a9e",
                                "digests": {
                                    "md5": "61ad7871532d4ce2d77fac2579237a9e",
                                    "sha256": "dddddd",
                                },
                                "downloads": 775920,
                                "filename": "enum34-1.1.6.zip",
                                "packagetype": "sdist",
                                "path": "e8/26/enum34-1.1.6.zip",
                                "size": 44773,
                            },
                        ]
                    },
                }
            )

        raise NotImplementedError(url)

    murlopen.side_effect = mocked_get

    with tmpfile() as filename:
        before = (
            """
# This is comment. Ignore this.

requests[security]==1.2.3 \\
    --hash=sha256:99dcfdaae
hashin==0.9 \\
    --hash=sha256:12ce5c2ef718
enum34==1.1.5; python_version <= '3.4' \\
    --hash=sha256:12ce5c2ef718

        """.strip()
            + "\n"
        )
        with open(filename, "w") as f:
            f.write(before)

        # Basically means we're saying "No" to all of them.
        with mock.patch("hashin.input", return_value="N"):
            retcode = hashin.run(None, filename, "sha256", interactive=True)
        assert retcode == 0

        with open(filename) as f:
            output = f.read()
            assert output == before

        questions = []

        def mock_input(question):
            questions.append(question)
            if len(questions) == 1:
                # First one is "requests[security]"
                return ""  # Default is "yes"
            elif len(questions) == 2:
                return "N"
            elif len(questions) == 3:
                return "Y"

        with mock.patch("hashin.input") as mocked_input:
            mocked_input.side_effect = mock_input
            retcode = hashin.run(None, filename, "sha256", interactive=True)
        assert retcode == 0

        # The expected output is that only "requests[security]" and "enum34"
        # get updated.
        expected = (
            """
# This is comment. Ignore this.

requests[security]==1.2.4 \\
    --hash=sha256:dededede
hashin==0.9 \\
    --hash=sha256:12ce5c2ef718
enum34==1.1.6; python_version <= "3.4" \\
    --hash=sha256:aaaaa \\
    --hash=sha256:bbbbb \\
    --hash=sha256:ccccc \\
    --hash=sha256:dddddd
        """.strip()
            + "\n"
        )
        with open(filename) as f:
            output = f.read()
            assert output == expected


def test_run_interactive_quit_and_accept_all(murlopen, tmpfile, capsys):
    def mocked_get(url, **options):

        if url == "https://pypi.org/pypi/hashin/json":
            return _Response(
                {
                    "info": {"version": "0.10", "name": "hashin"},
                    "releases": {
                        "0.10": [
                            {
                                "url": "https://pypi.org/packages/2.7/p/hashin/hashin-0.10-py2-none-any.whl",
                                "digests": {"sha256": "aaaaa"},
                            },
                            {
                                "url": "https://pypi.org/packages/3.3/p/hashin/hashin-0.10-py3-none-any.whl",
                                "digests": {"sha256": "bbbbb"},
                            },
                            {
                                "url": "https://pypi.org/packages/source/p/hashin/hashin-0.10.tar.gz",
                                "digests": {"sha256": "ccccc"},
                            },
                        ]
                    },
                }
            )
        elif url == "https://pypi.org/pypi/requests/json":
            return _Response(
                {
                    "info": {"version": "1.2.4", "name": "requests"},
                    "releases": {
                        "1.2.4": [
                            {
                                "url": "https://pypi.org/packages/source/p/requests/requests-1.2.4.tar.gz",
                                "digests": {"sha256": "dededede"},
                            }
                        ]
                    },
                }
            )
        if url == "https://pypi.org/pypi/enum34/json":
            return _Response(
                {
                    "info": {"version": "1.1.6", "name": "enum34"},
                    "releases": {
                        "1.1.6": [
                            {
                                "has_sig": False,
                                "upload_time": "2016-05-16T03:31:13",
                                "comment_text": "",
                                "python_version": "py2",
                                "url": "https://pypi.org/packages/c5/db/enum34-1.1.6-py2-none-any.whl",
                                "digests": {
                                    "md5": "68f6982cc07dde78f4b500db829860bd",
                                    "sha256": "aaaaa",
                                },
                                "md5_digest": "68f6982cc07dde78f4b500db829860bd",
                                "downloads": 4297423,
                                "filename": "enum34-1.1.6-py2-none-any.whl",
                                "packagetype": "bdist_wheel",
                                "path": "c5/db/enum34-1.1.6-py2-none-any.whl",
                                "size": 12427,
                            },
                            {
                                "has_sig": False,
                                "upload_time": "2016-05-16T03:31:19",
                                "comment_text": "",
                                "python_version": "py3",
                                "url": "https://pypi.org/packages/af/42/enum34-1.1.6-py3-none-any.whl",
                                "md5_digest": "a63ecb4f0b1b85fb69be64bdea999b43",
                                "digests": {
                                    "md5": "a63ecb4f0b1b85fb69be64bdea999b43",
                                    "sha256": "bbbbb",
                                },
                                "downloads": 98598,
                                "filename": "enum34-1.1.6-py3-none-any.whl",
                                "packagetype": "bdist_wheel",
                                "path": "af/42/enum34-1.1.6-py3-none-any.whl",
                                "size": 12428,
                            },
                            {
                                "has_sig": False,
                                "upload_time": "2016-05-16T03:31:30",
                                "comment_text": "",
                                "python_version": "source",
                                "url": "https://pypi.org/packages/bf/3e/enum34-1.1.6.tar.gz",
                                "md5_digest": "5f13a0841a61f7fc295c514490d120d0",
                                "digests": {
                                    "md5": "5f13a0841a61f7fc295c514490d120d0",
                                    "sha256": "ccccc",
                                },
                                "downloads": 188090,
                                "filename": "enum34-1.1.6.tar.gz",
                                "packagetype": "sdist",
                                "path": "bf/3e/enum34-1.1.6.tar.gz",
                                "size": 40048,
                            },
                            {
                                "has_sig": False,
                                "upload_time": "2016-05-16T03:31:48",
                                "comment_text": "",
                                "python_version": "source",
                                "url": "https://pypi.org/packages/e8/26/enum34-1.1.6.zip",
                                "md5_digest": "61ad7871532d4ce2d77fac2579237a9e",
                                "digests": {
                                    "md5": "61ad7871532d4ce2d77fac2579237a9e",
                                    "sha256": "dddddd",
                                },
                                "downloads": 775920,
                                "filename": "enum34-1.1.6.zip",
                                "packagetype": "sdist",
                                "path": "e8/26/enum34-1.1.6.zip",
                                "size": 44773,
                            },
                        ]
                    },
                }
            )

        raise NotImplementedError(url)

    murlopen.side_effect = mocked_get

    with tmpfile() as filename:
        before = (
            """
# This is comment. Ignore this.

requests[security]==1.2.3 \\
    --hash=sha256:99dcfdaae
hashin==0.9 \\
    --hash=sha256:12ce5c2ef718
enum34==1.1.5; python_version <= '3.4' \\
    --hash=sha256:12ce5c2ef718

        """.strip()
            + "\n"
        )
        with open(filename, "w") as f:
            f.write(before)

        questions = []

        def mock_input(question):
            questions.append(question)
            if len(questions) == 1:
                return "q"
            elif len(questions) == 2:
                return "A"
            raise NotImplementedError(questions)

        with mock.patch("hashin.input") as mocked_input:
            mocked_input.side_effect = mock_input
            retcode = hashin.run(None, filename, "sha256", interactive=True)
        assert retcode != 0
        assert len(questions) == 1

        with open(filename) as f:
            output = f.read()
            assert output == before

        with mock.patch("hashin.input") as mocked_input:
            mocked_input.side_effect = mock_input
            retcode = hashin.run(None, filename, "sha256", interactive=True)
        assert retcode == 0

        # The expected output is that only "requests[security]" and "enum34"
        # get updated.
        expected = (
            """
# This is comment. Ignore this.

requests[security]==1.2.4 \\
    --hash=sha256:dededede
hashin==0.10 \\
    --hash=sha256:aaaaa \\
    --hash=sha256:bbbbb \\
    --hash=sha256:ccccc
enum34==1.1.6; python_version <= "3.4" \\
    --hash=sha256:aaaaa \\
    --hash=sha256:bbbbb \\
    --hash=sha256:ccccc \\
    --hash=sha256:dddddd
        """.strip()
            + "\n"
        )
        with open(filename) as f:
            output = f.read()
            assert output == expected

        # No more questions were asked of `input()`.
        assert len(questions) == 2


def test_run_without_specific_version(murlopen, tmpfile):
    def mocked_get(url, **options):
        if url == "https://pypi.org/pypi/hashin/json":
            return _Response(
                {
                    "info": {"version": "0.10", "name": "hashin"},
                    "releases": {
                        "0.10": [
                            {
                                "url": "https://pypi.org/packages/2.7/p/hashin/hashin-0.10-py2-none-any.whl",
                                "digests": {"sha256": "aaaaa"},
                            },
                            {
                                "url": "https://pypi.org/packages/3.3/p/hashin/hashin-0.10-py3-none-any.whl",
                                "digests": {"sha256": "bbbbb"},
                            },
                            {
                                "url": "https://pypi.org/packages/source/p/hashin/hashin-0.10.tar.gz",
                                "digests": {"sha256": "ccccc"},
                            },
                        ]
                    },
                }
            )

        raise NotImplementedError(url)

    murlopen.side_effect = mocked_get

    with tmpfile() as filename:
        with open(filename, "w") as f:
            f.write("")

        retcode = hashin.run("hashin", filename, "sha256", verbose=True)

        assert retcode == 0
        with open(filename) as f:
            output = f.read()
        assert output.startswith("hashin==0.10")


def test_run_contained_names(murlopen, tmpfile):
    """
    This is based on https://github.com/peterbe/hashin/issues/35
    which was a real bug discovered in hashin 0.8.0.
    It happens because the second package's name is entirely contained
    in the first package's name.
    """

    def mocked_get(url, **options):
        if url == "https://pypi.org/pypi/django-redis/json":
            return _Response(
                {
                    "info": {"version": "4.7.0", "name": "django-redis"},
                    "releases": {
                        "4.7.0": [
                            {
                                "url": "https://pypi.org/packages/source/p/django-redis/django-redis-4.7.0.tar.gz",
                                "digests": {"sha256": "aaaaa"},
                            }
                        ]
                    },
                }
            )
        elif (
            url
            == "https://pypi.org/packages/source/p/django-redis/django-redis-4.7.0.tar.gz"
        ):
            return _Response(b"Some tarball content\n")
        elif url == "https://pypi.org/pypi/redis/json":
            return _Response(
                {
                    "info": {"version": "2.10.5", "name": "redis"},
                    "releases": {
                        "2.10.5": [
                            {
                                "url": "https://pypi.org/packages/source/p/redis/redis-2.10.5.tar.gz",
                                "digests": {"sha256": "bbbbb"},
                            }
                        ]
                    },
                }
            )

        raise NotImplementedError(url)

    murlopen.side_effect = mocked_get

    with tmpfile() as filename:
        with open(filename, "w") as f:
            f.write("")

        retcode = hashin.run("django-redis==4.7.0", filename, "sha256", verbose=True)

        assert retcode == 0
        with open(filename) as f:
            output = f.read()
        assert output.endswith("\n")
        lines = output.splitlines()
        assert "django-redis==4.7.0 \\" in lines
        assert len(lines) == 2

        # Now install the next package whose name is contained
        # in the first one.
        retcode = hashin.run("redis==2.10.5", filename, "sha256", verbose=True)

        assert retcode == 0
        with open(filename) as f:
            output = f.read()
        assert output.endswith("\n")
        lines = output.splitlines()
        assert "django-redis==4.7.0 \\" in lines
        assert "redis==2.10.5 \\" in lines
        assert len(lines) == 4


def test_run_case_insensitive(murlopen, tmpfile):
    """No matter how you run the cli with a package's case typing,
    it should find it and correct the cast typing per what it is
    inside the PyPI data."""

    def mocked_get(url, **options):
        if url == "https://pypi.org/pypi/hashin/json":
            return _Response(
                {
                    "info": {"version": "0.11", "name": "hashin"},
                    "releases": {
                        "0.11": [
                            {
                                "url": "https://pypi.org/packages/source/p/hashin/hashin-0.11.tar.gz",
                                "digests": {"sha256": "bbbbb"},
                            }
                        ],
                        "0.10": [
                            {
                                "url": "https://pypi.org/packages/source/p/hashin/hashin-0.10.tar.gz",
                                "digests": {"sha256": "aaaaa"},
                            }
                        ],
                    },
                }
            )
        elif url == "https://pypi.org/pypi/hashin/json":
            return _Response(
                {
                    "info": {"version": "0.11", "name": "hashin"},
                    "releases": {
                        "0.11": [
                            {
                                "url": "https://pypi.org/packages/source/p/hashin/hashin-0.11.tar.gz",
                                "digests": {"sha256": "bbbbb"},
                            }
                        ],
                        "0.10": [
                            {
                                "url": "https://pypi.org/packages/source/p/hashin/hashin-0.10.tar.gz",
                                "digests": {"sha256": "aaaaa"},
                            }
                        ],
                    },
                }
            )
        elif url == "https://pypi.org/pypi/requests/json":
            return _Response(
                {
                    "info": {"version": "1.2.4", "name": "requests"},
                    "releases": {
                        "1.2.4": [
                            {
                                "url": "https://pypi.org/packages/source/p/requests/requests-1.2.4.tar.gz",
                                "digests": {"sha256": "dededede"},
                            }
                        ]
                    },
                }
            )
        if url == "https://pypi.org/pypi/enum34/json":
            return _Response(
                {
                    "info": {"version": "1.1.6", "name": "enum34"},
                    "releases": {
                        "1.1.6": [
                            {
                                "has_sig": False,
                                "upload_time": "2016-05-16T03:31:13",
                                "comment_text": "",
                                "python_version": "py2",
                                "url": "https://pypi.org/packages/c5/db/enum34-1.1.6-py2-none-any.whl",
                                "digests": {
                                    "md5": "68f6982cc07dde78f4b500db829860bd",
                                    "sha256": "aaaaa",
                                },
                                "md5_digest": "68f6982cc07dde78f4b500db829860bd",
                                "downloads": 4297423,
                                "filename": "enum34-1.1.6-py2-none-any.whl",
                                "packagetype": "bdist_wheel",
                                "path": "c5/db/enum34-1.1.6-py2-none-any.whl",
                                "size": 12427,
                            },
                            {
                                "has_sig": False,
                                "upload_time": "2016-05-16T03:31:19",
                                "comment_text": "",
                                "python_version": "py3",
                                "url": "https://pypi.org/packages/af/42/enum34-1.1.6-py3-none-any.whl",
                                "md5_digest": "a63ecb4f0b1b85fb69be64bdea999b43",
                                "digests": {
                                    "md5": "a63ecb4f0b1b85fb69be64bdea999b43",
                                    "sha256": "bbbbb",
                                },
                                "downloads": 98598,
                                "filename": "enum34-1.1.6-py3-none-any.whl",
                                "packagetype": "bdist_wheel",
                                "path": "af/42/enum34-1.1.6-py3-none-any.whl",
                                "size": 12428,
                            },
                            {
                                "has_sig": False,
                                "upload_time": "2016-05-16T03:31:30",
                                "comment_text": "",
                                "python_version": "source",
                                "url": "https://pypi.org/packages/bf/3e/enum34-1.1.6.tar.gz",
                                "md5_digest": "5f13a0841a61f7fc295c514490d120d0",
                                "digests": {
                                    "md5": "5f13a0841a61f7fc295c514490d120d0",
                                    "sha256": "ccccc",
                                },
                                "downloads": 188090,
                                "filename": "enum34-1.1.6.tar.gz",
                                "packagetype": "sdist",
                                "path": "bf/3e/enum34-1.1.6.tar.gz",
                                "size": 40048,
                            },
                            {
                                "has_sig": False,
                                "upload_time": "2016-05-16T03:31:48",
                                "comment_text": "",
                                "python_version": "source",
                                "url": "https://pypi.org/packages/e8/26/enum34-1.1.6.zip",
                                "md5_digest": "61ad7871532d4ce2d77fac2579237a9e",
                                "digests": {
                                    "md5": "61ad7871532d4ce2d77fac2579237a9e",
                                    "sha256": "dddddd",
                                },
                                "downloads": 775920,
                                "filename": "enum34-1.1.6.zip",
                                "packagetype": "sdist",
                                "path": "e8/26/enum34-1.1.6.zip",
                                "size": 44773,
                            },
                        ]
                    },
                }
            )

        raise NotImplementedError(url)

    murlopen.side_effect = mocked_get

    with tmpfile() as filename:
        with pytest.raises(FileNotFoundError):
            hashin.run(None, filename, "sha256")

        with open(filename, "w") as f:
            f.write("# This is comment. Ignore this.\n")
            f.write("\n")
            f.write("requests[security]==1.2.3 \\\n")
            f.write("    --hash=sha256:99dcfdaae\n")
            f.write("hashin==0.11 \\\n")
            f.write("    --hash=sha256:a84b8c9ab623\n")
            f.write("enum34==1.1.5; python_version <= '3.4' \\\n")
            f.write("    --hash=sha256:12ce5c2ef718\n")
            f.write("\n")

        retcode = hashin.run(None, filename, "sha256", verbose=True)

        assert retcode == 0
        with open(filename) as f:
            output = f.read()

        assert "requests[security]==1.2.3" not in output
        assert "requests[security]==1.2.4" in output
        # This one didn't need to be updated.
        assert "hashin==0.11" in output
        assert 'enum34==1.1.5; python_version <= "3.4"' not in output
        assert 'enum34==1.1.6; python_version <= "3.4"' in output


def test_run_update_all(murlopen, tmpfile):
    """The --update-all flag will extra all the names from the existing
    requirements file, and check with pypi.org if there's a new version."""

    def mocked_get(url, **options):
        if url == "https://pypi.org/pypi/HAShin/json":
            return _Response(
                "",
                status_code=301,
                headers={"location": "https://pypi.org/pypi/hashin/json"},
            )
        elif url == "https://pypi.org/pypi/hashIN/json":
            return _Response(
                "",
                status_code=301,
                headers={"location": "https://pypi.org/pypi/hashin/json"},
            )
        elif url == "https://pypi.org/pypi/hashin/json":
            return _Response(
                {
                    "info": {"version": "0.11", "name": "hashin"},
                    "releases": {
                        "0.11": [
                            {
                                "url": "https://pypi.org/packages/source/p/hashin/hashin-0.11.tar.gz",
                                "digests": {"sha256": "bbbbb"},
                            }
                        ],
                        "0.10": [
                            {
                                "url": "https://pypi.org/packages/source/p/hashin/hashin-0.10.tar.gz",
                                "digests": {"sha256": "aaaaa"},
                            }
                        ],
                    },
                }
            )

        raise NotImplementedError(url)

    murlopen.side_effect = mocked_get

    with tmpfile() as filename:
        with open(filename, "w") as f:
            f.write("")

        retcode = hashin.run("HAShin==0.10", filename, "sha256", verbose=True)

        assert retcode == 0
        with open(filename) as f:
            output = f.read()
        assert output.endswith("\n")
        lines = output.splitlines()
        assert lines[0] == "hashin==0.10 \\"

        # Change version
        retcode = hashin.run("hashIN==0.11", filename, "sha256")
        assert retcode == 0
        with open(filename) as f:
            output = f.read()
        assert output.endswith("\n")
        lines = output.splitlines()
        assert lines[0] == "hashin==0.11 \\"


def test_run_dry(murlopen, tmpfile, capsys):
    """dry run should edit the requirements.txt file and print
    hashes and package name in the console
    """

    def mocked_get(url, **options):
        if url == "https://pypi.org/pypi/hashin/json":
            return _Response(
                {
                    "info": {"version": "0.11", "name": "hashin"},
                    "releases": {
                        "0.11": [
                            {
                                "url": "https://pypi.org/packages/source/p/hashin/hashin-0.11.tar.gz",
                                "digests": {"sha256": "bbbbb"},
                            }
                        ],
                        "0.10": [
                            {
                                "url": "https://pypi.org/packages/source/p/hashin/hashin-0.10.tar.gz",
                                "digests": {"sha256": "aaaaa"},
                            }
                        ],
                    },
                }
            )

    murlopen.side_effect = mocked_get

    with tmpfile() as filename:
        with open(filename, "w") as f:
            f.write("")

        retcode = hashin.run(
            "hashin==0.10", filename, "sha256", verbose=False, dry_run=True
        )
        assert retcode == 0

        # verify that nothing has been written to file
        with open(filename) as f:
            output = f.read()
        assert not output

    # Check dry run output
    captured = capsys.readouterr()
    out_lines = captured.out.splitlines()
    assert "+hashin==0.10" in out_lines[3]
    assert "+--hash=sha256:aaaaa" in out_lines[4].replace(" ", "")


def test_run_dry_multiple_packages(murlopen, tmpfile, capsys):
    """dry run should edit the requirements.txt file and print
    hashes and package name in the console
    """

    def mocked_get(url, **options):
        if url == "https://pypi.org/pypi/hashin/json":
            return _Response(
                {
                    "info": {"version": "0.11", "name": "hashin"},
                    "releases": {
                        "0.11": [
                            {
                                "url": "https://pypi.org/packages/source/p/hashin/hashin-0.11.tar.gz",
                                "digests": {"sha256": "bbbbb"},
                            }
                        ],
                        "0.10": [
                            {
                                "url": "https://pypi.org/packages/source/p/hashin/hashin-0.10.tar.gz",
                                "digests": {"sha256": "aaaaa"},
                            }
                        ],
                    },
                }
            )
        if url == "https://pypi.org/pypi/requests/json":
            return _Response(
                {
                    "info": {"version": "1.2.4", "name": "requests"},
                    "releases": {
                        "1.2.4": [
                            {
                                "url": "https://pypi.org/packages/source/p/requests/requests-1.2.4.tar.gz",
                                "digests": {"sha256": "dededede"},
                            }
                        ]
                    },
                }
            )

        raise NotImplementedError(url)

    murlopen.side_effect = mocked_get

    with tmpfile() as filename:
        with open(filename, "w") as f:
            f.write("")

        retcode = hashin.run(
            ["hashin", "requests"], filename, "sha256", verbose=False, dry_run=True
        )
        assert retcode == 0

        # verify that nothing has been written to file
        with open(filename) as f:
            output = f.read()
        assert not output

    # Check dry run output
    captured = capsys.readouterr()
    output = captured.out
    out_lines = output.splitlines()
    assert output.count("Old") == 1
    assert output.count("New") == 1
    assert "+hashin==0.11" in out_lines[3]
    assert "+--hash=sha256:bbbbb" in out_lines[4].replace(" ", "")
    assert "+requests==1.2.4" in out_lines[5]
    assert "+--hash=sha256:dededede" in out_lines[6].replace(" ", "")


def test_run_pep_0496(murlopen, tmpfile):
    """
    Properly pass through specifiers which look like:

        enum==1.1.6; python_version <= '3.4'

    These can include many things besides python_version; see
    https://www.python.org/dev/peps/pep-0496/
    """

    def mocked_get(url, **options):
        if url == "https://pypi.org/pypi/enum34/json":
            return _Response(
                {
                    "info": {"version": "1.1.6", "name": "enum34"},
                    "releases": {
                        "1.1.6": [
                            {
                                "has_sig": False,
                                "upload_time": "2016-05-16T03:31:13",
                                "comment_text": "",
                                "python_version": "py2",
                                "url": "https://pypi.org/packages/c5/db/enum34-1.1.6-py2-none-any.whl",
                                "digests": {
                                    "md5": "68f6982cc07dde78f4b500db829860bd",
                                    "sha256": "aaaaa",
                                },
                                "md5_digest": "68f6982cc07dde78f4b500db829860bd",
                                "downloads": 4297423,
                                "filename": "enum34-1.1.6-py2-none-any.whl",
                                "packagetype": "bdist_wheel",
                                "path": "c5/db/enum34-1.1.6-py2-none-any.whl",
                                "size": 12427,
                            },
                            {
                                "has_sig": False,
                                "upload_time": "2016-05-16T03:31:19",
                                "comment_text": "",
                                "python_version": "py3",
                                "url": "https://pypi.org/packages/af/42/enum34-1.1.6-py3-none-any.whl",
                                "md5_digest": "a63ecb4f0b1b85fb69be64bdea999b43",
                                "digests": {
                                    "md5": "a63ecb4f0b1b85fb69be64bdea999b43",
                                    "sha256": "bbbbb",
                                },
                                "downloads": 98598,
                                "filename": "enum34-1.1.6-py3-none-any.whl",
                                "packagetype": "bdist_wheel",
                                "path": "af/42/enum34-1.1.6-py3-none-any.whl",
                                "size": 12428,
                            },
                            {
                                "has_sig": False,
                                "upload_time": "2016-05-16T03:31:30",
                                "comment_text": "",
                                "python_version": "source",
                                "url": "https://pypi.org/packages/bf/3e/enum34-1.1.6.tar.gz",
                                "md5_digest": "5f13a0841a61f7fc295c514490d120d0",
                                "digests": {
                                    "md5": "5f13a0841a61f7fc295c514490d120d0",
                                    "sha256": "ccccc",
                                },
                                "downloads": 188090,
                                "filename": "enum34-1.1.6.tar.gz",
                                "packagetype": "sdist",
                                "path": "bf/3e/enum34-1.1.6.tar.gz",
                                "size": 40048,
                            },
                            {
                                "has_sig": False,
                                "upload_time": "2016-05-16T03:31:48",
                                "comment_text": "",
                                "python_version": "source",
                                "url": "https://pypi.org/packages/e8/26/enum34-1.1.6.zip",
                                "md5_digest": "61ad7871532d4ce2d77fac2579237a9e",
                                "digests": {
                                    "md5": "61ad7871532d4ce2d77fac2579237a9e",
                                    "sha256": "dddddd",
                                },
                                "downloads": 775920,
                                "filename": "enum34-1.1.6.zip",
                                "packagetype": "sdist",
                                "path": "e8/26/enum34-1.1.6.zip",
                                "size": 44773,
                            },
                        ]
                    },
                }
            )

        raise NotImplementedError(url)

    murlopen.side_effect = mocked_get

    with tmpfile() as filename:
        with open(filename, "w") as f:
            f.write("")

        retcode = hashin.run(
            "enum34==1.1.6; python_version <= '3.4'", filename, "sha256", verbose=True
        )

        assert retcode == 0
        with open(filename) as f:
            output = f.read()
        assert output.endswith("\n")
        lines = output.splitlines()
        assert lines[0] == "enum34==1.1.6; python_version <= '3.4' \\"


def test_filter_releases():
    releases = [
        {"url": "https://pypi.org/packages/2.7/p/hashin/hashin-0.10-py2-none-any.whl"},
        {"url": "https://pypi.org/packages/3.3/p/hashin/hashin-0.10-py3-none-any.whl"},
        {"url": "https://pypi.org/packages/source/p/hashin/hashin-0.10.tar.gz"},
    ]

    # With no filters, no releases are included
    assert hashin.filter_releases(releases, []) == []

    # With filters, other Python versions are filtered out.
    filtered = hashin.filter_releases(releases, ["py2"])
    assert filtered == [releases[0]]

    # Multiple filters work
    filtered = hashin.filter_releases(releases, ["py3", "source"])
    assert filtered == [releases[1], releases[2]]


def test_release_url_metadata_python():
    url = "https://pypi.org/packages/3.4/P/Pygments/Pygments-2.1-py3-none-any.whl"
    assert hashin.release_url_metadata(url) == {
        "package": "Pygments",
        "version": "2.1",
        "python_version": "py3",
        "abi": "none",
        "platform": "any",
        "format": "whl",
    }
    url = "https://pypi.org/packages/2.7/J/Jinja2/Jinja2-2.8-py2.py3-none-any.whl"
    assert hashin.release_url_metadata(url) == {
        "package": "Jinja2",
        "version": "2.8",
        "python_version": "py2.py3",
        "abi": "none",
        "platform": "any",
        "format": "whl",
    }
    url = "https://pypi.org/packages/cp35/c/cffi/cffi-1.5.2-cp35-none-win32.whl"
    assert hashin.release_url_metadata(url) == {
        "package": "cffi",
        "version": "1.5.2",
        "python_version": "cp35",
        "abi": "none",
        "platform": "win32",
        "format": "whl",
    }

    url = (
        "https://pypi.org/packages/source/f/factory_boy/"
        "factory_boy-2.6.0.tar.gz#md5=d61ee02c6ac8d992f228c0346bd52f32"
    )
    assert hashin.release_url_metadata(url) == {
        "package": "factory_boy",
        "version": "2.6.0",
        "python_version": "source",
        "abi": None,
        "platform": None,
        "format": "tar.gz",
    }

    url = (
        "https://pypi.org/packages/source/d/django-reversion/"
        "django-reversion-1.10.0.tar.gz"
    )
    assert hashin.release_url_metadata(url) == {
        "package": "django-reversion",
        "version": "1.10.0",
        "python_version": "source",
        "abi": None,
        "platform": None,
        "format": "tar.gz",
    }

    url = "https://pypi.org/packages/2.6/g/greenlet/greenlet-0.4.9-py2.6-win-amd64.egg"
    assert hashin.release_url_metadata(url) == {
        "package": "greenlet",
        "version": "0.4.9",
        "python_version": "py2.6",
        "abi": None,
        "platform": "win-amd64",
        "format": "egg",
    }

    url = "https://pypi.org/packages/2.4/p/pytz/pytz-2015.7-py2.4.egg"
    assert hashin.release_url_metadata(url) == {
        "package": "pytz",
        "version": "2015.7",
        "python_version": "py2.4",
        "abi": None,
        "platform": None,
        "format": "egg",
    }

    url = "https://files.pythonhosted.org/packages/26/01/0330e3ba13628827f10fcd6c3c8d778a5aa3e4d0a09d05619f074ba2d87e/nltk-3.2.4.win32.exe"
    assert hashin.release_url_metadata(url) == {
        "package": "nltk",
        "version": "3.2.4",
        "python_version": mock.ANY,
        "abi": None,
        "platform": None,
        "format": "exe",
    }

    url = "https://pypi.org/packages/2.7/g/gevent/gevent-1.1.0.win-amd64-py2.7.exe"
    assert hashin.release_url_metadata(url) == {
        "package": "gevent",
        "version": "1.1.0.win",
        "python_version": "py2.7",
        "abi": None,
        "platform": "amd64",
        "format": "exe",
    }

    url = "https://pypi.org/packages/d5/0d/445186a82bbcc75166a507eff586df683c73641e7d6bb7424a44426dca71/Django-1.8.12-py2.py3-none-any.whl"
    assert hashin.release_url_metadata(url) == {
        "package": "Django",
        "version": "1.8.12",
        "python_version": "py2.py3",
        "abi": "none",
        "platform": "any",
        "format": "whl",
    }

    # issue 32
    url = "https://pypi.org/packages/a4/ae/65500d0becffe3dd6671fbdc6010cc0c4a8b715dbd94315ba109bbc54bc5/turbine-0.0.3.linux-x86_64.tar.gz"
    assert hashin.release_url_metadata(url) == {
        "package": "turbine",
        "version": "0.0.3.linux",
        "python_version": "source",
        "abi": None,
        "platform": "x86_64",
        "format": "tar.gz",
    }


def test_expand_python_version():
    assert sorted(hashin.expand_python_version("2.7")) == [
        "2.7",
        "cp27",
        "py2",
        "py2.7",
        "py2.py3",
        "py27",
        "source",
    ]

    assert sorted(hashin.expand_python_version("3.5")) == [
        "3.5",
        "cp35",
        "py2.py3",
        "py3",
        "py3.5",
        "py35",
        "source",
    ]


def test_get_package_hashes(murlopen):
    def mocked_get(url, **options):
        if url == "https://pypi.org/pypi/hashin/json":
            return _Response(
                {
                    "info": {"version": "0.10", "name": "hashin"},
                    "releases": {
                        "0.10": [
                            {
                                "url": "https://pypi.org/packages/2.7/p/hashin/hashin-0.10-py2-none-any.whl",
                                "digests": {"sha256": "aaaaa"},
                            },
                            {
                                "url": "https://pypi.org/packages/3.3/p/hashin/hashin-0.10-py3-none-any.whl",
                                "digests": {"sha256": "bbbbb"},
                            },
                            {
                                "url": "https://pypi.org/packages/source/p/hashin/hashin-0.10.tar.gz",
                                "digests": {"sha256": "ccccc"},
                            },
                        ]
                    },
                }
            )

        raise NotImplementedError(url)

    murlopen.side_effect = mocked_get

    result = hashin.get_package_hashes(
        package="hashin", version="0.10", algorithm="sha256"
    )

    expected = {
        "package": "hashin",
        "version": "0.10",
        "hashes": [{"hash": "aaaaa"}, {"hash": "bbbbb"}, {"hash": "ccccc"}],
    }

    assert result == expected


def test_get_package_hashes_package_not_found(murlopen):
    def mocked_get(url, **options):
        if url == "https://pypi.org/pypi/gobblygook/json":
            if HTTPError:
                raise HTTPError(url, 404, "Page not found", {}, None)
            else:
                return _Response({}, status_code=404)

        if url == "https://pypi.org/pypi/troublemaker/json":
            if HTTPError:
                raise HTTPError(url, 500, "Something went wrong", {}, None)
            else:
                return _Response({}, status_code=500)

        raise NotImplementedError(url)

    murlopen.side_effect = mocked_get

    with pytest.raises(hashin.PackageNotFoundError) as exc_info:
        hashin.get_package_hashes(
            package="gobblygook", version="0.10", algorithm="sha256"
        )
    assert str(exc_info.value) == "https://pypi.org/pypi/gobblygook/json"

    # Errors left as is if not a 404
    with pytest.raises(hashin.PackageError):
        hashin.get_package_hashes(
            package="troublemaker", version="0.10", algorithm="sha256"
        )


def test_get_package_hashes_unknown_algorithm(murlopen, capsys):
    def mocked_get(url, **options):
        if url == "https://pypi.org/pypi/hashin/json":
            return _Response(
                {
                    "info": {"version": "0.10", "name": "hashin"},
                    "releases": {
                        "0.10": [
                            {
                                "url": "https://pypi.org/packages/2.7/p/hashin/hashin-0.10-py2-none-any.whl",
                                "digests": {"sha256": "aaaaa"},
                            },
                            {
                                "url": "https://pypi.org/packages/3.3/p/hashin/hashin-0.10-py3-none-any.whl",
                                "digests": {"sha256": "bbbbb"},
                            },
                            {
                                "url": "https://pypi.org/packages/source/p/hashin/hashin-0.10.tar.gz",
                                "digests": {"sha256": "ccccc"},
                            },
                        ]
                    },
                }
            )
        elif (
            url == "https://pypi.org/packages/2.7/p/hashin/hashin-0.10-py2-none-any.whl"
        ):
            return _Response(b"Some py2 wheel content\n")
        elif (
            url == "https://pypi.org/packages/3.3/p/hashin/hashin-0.10-py3-none-any.whl"
        ):
            return _Response(b"Some py3 wheel content\n")
        elif url == "https://pypi.org/packages/source/p/hashin/hashin-0.10.tar.gz":
            return _Response(b"Some tarball content\n")

        raise NotImplementedError(url)

    murlopen.side_effect = mocked_get

    result = hashin.get_package_hashes(
        package="hashin", version="0.10", algorithm="sha512", verbose=True
    )
    captured = capsys.readouterr()
    out_lines = captured.out.splitlines()
    assert (
        "Found URL https://pypi.org/packages/2.7/p/hashin/hashin-0.10-py2-none-any.whl"
        in out_lines[1]
    )

    expected = {
        "package": "hashin",
        "version": "0.10",
        "hashes": [
            {
                "hash": "45d1c5d2237a3b4f78b4198709fb2ecf1f781c8234ce3d94356f2100a36739433952c6c13b2843952f608949e6baa9f95055a314487cd8fb3f9d76522d8edb50"
            },
            {
                "hash": "0d63bf4c115154781846ecf573049324f06b021a1d4b92da4fae2bf491da2b83a13096b14d73e73cefad36855f4fa936bac4b2357dabf05a2b1e7329ff1e5455"
            },
            {
                "hash": "c32e6d9fb09dc36ab9222c4606a1f43a2dcc183a8c64bdd9199421ef779072c174fa044b155babb12860cf000e36bc4d358694fa22420c997b1dd75b623d4daa"
            },
        ],
    }

    assert result == expected


def test_get_package_hashes_without_version(murlopen, capsys):
    def mocked_get(url, **options):
        if url == "https://pypi.org/pypi/hashin/json":
            return _Response(
                {
                    "info": {"version": "0.10", "name": "hashin"},
                    "releases": {
                        "0.10": [
                            {
                                "url": "https://pypi.org/packages/2.7/p/hashin/hashin-0.10-py2-none-any.whl",
                                "digests": {"sha256": "aaaaa"},
                            },
                            {
                                "url": "https://pypi.org/packages/3.3/p/hashin/hashin-0.10-py3-none-any.whl",
                                "digests": {"sha256": "bbbbb"},
                            },
                            {
                                "url": "https://pypi.org/packages/source/p/hashin/hashin-0.10.tar.gz",
                                "digests": {"sha256": "ccccc"},
                            },
                        ]
                    },
                }
            )
        elif url == "https://pypi.org/pypi/uggamugga/json":
            return _Response(
                {
                    "info": {"version": "1.2.3", "name": "uggamugga"},
                    "releases": {},  # Note!
                }
            )

        raise NotImplementedError(url)

    murlopen.side_effect = mocked_get

    result = hashin.get_package_hashes(package="hashin", verbose=True)
    assert result["package"] == "hashin"
    assert result["version"] == "0.10"
    assert result["hashes"]
    captured = capsys.readouterr()
    assert "Latest version for hashin is 0.10" in captured.out

    # Let's do it again and mess with a few things.
    # First specify python_versions.
    result = hashin.get_package_hashes(
        package="hashin", verbose=True, python_versions=("3.5",)
    )
    assert len(result["hashes"]) == 2  # instead of 3
    # Specify an unrecognized python version
    with pytest.raises(hashin.PackageError):
        hashin.get_package_hashes(package="hashin", python_versions=("2.99999",))

    # Look for a package without any releases
    with pytest.raises(hashin.PackageError):
        hashin.get_package_hashes(package="uggamugga")


def test_with_extras_syntax(murlopen, tmpfile):
    """When you want to add the hashes of a package by using the
    "extras notation". E.g `requests[security]`.
    In this case, it should basically ignore the `[security]` part when
    doing the magic but get that back when putting the final result
    into the requirements file.
    """

    def mocked_get(url, **options):
        if url == "https://pypi.org/pypi/hashin/json":
            return _Response(
                {
                    "info": {"version": "0.10", "name": "hashin"},
                    "releases": {
                        "0.10": [
                            {
                                "url": "https://pypi.org/packages/source/p/hashin/hashin-0.10.tar.gz",
                                "digests": {"sha256": "ccccc"},
                            }
                        ]
                    },
                }
            )
        raise NotImplementedError(url)

    murlopen.side_effect = mocked_get

    with tmpfile() as filename:
        with open(filename, "w") as f:
            f.write("")

        retcode = hashin.run("hashin[stuff]", filename, "sha256")

        assert retcode == 0
        with open(filename) as f:
            output = f.read()
        assert "hashin[stuff]==0.10" in output


def test_extras_syntax_edit(murlopen, tmpfile):
    def mocked_get(url, **options):
        if url == "https://pypi.org/pypi/hashin/json":
            return _Response(
                {
                    "info": {"version": "0.10", "name": "hashin"},
                    "releases": {
                        "0.10": [
                            {
                                "url": "https://pypi.org/packages/source/p/hashin/hashin-0.10.tar.gz",
                                "digests": {"sha256": "ccccc"},
                            }
                        ]
                    },
                }
            )
        raise NotImplementedError(url)

    murlopen.side_effect = mocked_get

    with tmpfile() as filename:
        with open(filename, "w") as f:
            f.write("hashin==0.10\n")
            f.write("    --hash=sha256:ccccc\n")

        retcode = hashin.run("hashin[stuff]", filename, "sha256")

        assert retcode == 0
        with open(filename) as f:
            output = f.read()
        assert "hashin[stuff]==0.10" in output
        assert "hashin==0.10" not in output


def test_add_extra_extras_syntax_edit(murlopen, tmpfile):
    def mocked_get(url, **options):
        if url == "https://pypi.org/pypi/hashin/json":
            return _Response(
                {
                    "info": {"version": "0.10", "name": "hashin"},
                    "releases": {
                        "0.10": [
                            {
                                "url": "https://pypi.org/packages/source/p/hashin/hashin-0.10.tar.gz",
                                "digests": {"sha256": "ccccc"},
                            }
                        ]
                    },
                }
            )
        raise NotImplementedError(url)

    murlopen.side_effect = mocked_get

    with tmpfile() as filename:
        with open(filename, "w") as f:
            f.write("hashin[stuff]==0.10\n")
            f.write("    --hash=sha256:ccccc\n")

        retcode = hashin.run("hashin[extra,stuff]", filename, "sha256")

        assert retcode == 0
        with open(filename) as f:
            output = f.read()
        assert "hashin[extra,stuff]==0.10" in output
        assert "hashin==0.10" not in output
        assert "hashin[stuff]==0.10" not in output
        assert "hashin[extra]==0.10" not in output


def test_change_extra_extras_syntax_edit(murlopen, tmpfile):
    def mocked_get(url, **options):
        if url == "https://pypi.org/pypi/hashin/json":
            return _Response(
                {
                    "info": {"version": "0.10", "name": "hashin"},
                    "releases": {
                        "0.10": [
                            {
                                "url": "https://pypi.org/packages/source/p/hashin/hashin-0.10.tar.gz",
                                "digests": {"sha256": "ccccc"},
                            }
                        ]
                    },
                }
            )
        raise NotImplementedError(url)

    murlopen.side_effect = mocked_get

    with tmpfile() as filename:
        with open(filename, "w") as f:
            f.write("hashin[stuff]==0.10\n")
            f.write("    --hash=sha256:ccccc\n")

        retcode = hashin.run("hashin[different]", filename, "sha256")

        assert retcode == 0
        with open(filename) as f:
            output = f.read()
        assert "hashin[different]==0.10" in output
        assert "hashin[stuff]==0.10" not in output


def test_remove_extra_extras_syntax_edit(murlopen, tmpfile):
    def mocked_get(url, **options):
        if url == "https://pypi.org/pypi/hashin/json":
            return _Response(
                {
                    "info": {"version": "0.10", "name": "hashin"},
                    "releases": {
                        "0.10": [
                            {
                                "url": "https://pypi.org/packages/source/p/hashin/hashin-0.10.tar.gz",
                                "digests": {"sha256": "ccccc"},
                            }
                        ]
                    },
                }
            )
        raise NotImplementedError(url)

    murlopen.side_effect = mocked_get

    with tmpfile() as filename:
        with open(filename, "w") as f:
            f.write("hashin[stuff]==0.10\n")
            f.write("    --hash=sha256:ccccc\n")

        retcode = hashin.run("hashin", filename, "sha256")

        assert retcode == 0
        with open(filename) as f:
            output = f.read()
        assert "hashin==0.10" in output
        assert "hashin[stuff]==0.10" not in output


def test_interactive_upgrade_request(capsys):
    old = Requirement("hashin==0.9")
    old_version = old.specifier
    new = Requirement("hashin==0.10")
    new_version = new.specifier

    with mock.patch("hashin.input", return_value="Y "):
        assert hashin.interactive_upgrade_request(
            "hashin", old_version, new_version, print_header=True
        )

    captured = capsys.readouterr()
    assert "PACKAGE" in captured.out
    assert "\nhashin " in captured.out
    assert " 0.9 " in captured.out
    assert " 0.10 " in captured.out
    assert u"✓" in captured.out

    # This time, say no.
    with mock.patch("hashin.input", return_value="N"):
        assert not hashin.interactive_upgrade_request(
            "hashin", old_version, new_version
        )

    captured = capsys.readouterr()
    assert "PACKAGE" not in captured.out
    assert "hashin " in captured.out
    assert " 0.9 " in captured.out
    assert " 0.10 " in captured.out
    assert u"✘" in captured.out

    # This time, say yes to everything.
    with mock.patch("hashin.input", return_value="A"):
        with pytest.raises(hashin.InteractiveAll):
            hashin.interactive_upgrade_request("hashin", old_version, new_version)

    captured = capsys.readouterr()
    assert "hashin " in captured.out

    # This time, quit it.
    # This time, say yes to everything.
    with mock.patch("hashin.input", return_value="q "):
        with pytest.raises(hashin.InteractiveQuit):
            hashin.interactive_upgrade_request("hashin", old_version, new_version)

    captured = capsys.readouterr()
    assert "hashin " in captured.out
    # When you quit, it doesn't clear the last question.
    assert "?\n" in captured.out


def test_interactive_upgrade_request_repeat_question(capsys):
    old = Requirement("hashin==0.9")
    old_version = old.specifier
    new = Requirement("hashin==0.10")
    new_version = new.specifier

    questions = []

    def mock_input(question):
        questions.append(question)
        if len(questions) == 1:
            return "X"  # anything not recognized
        elif len(questions) == 2:
            return "Y"
        raise NotImplementedError(questions)

    with mock.patch("hashin.input") as mocked_input:
        mocked_input.side_effect = mock_input
        assert hashin.interactive_upgrade_request("hashin", old_version, new_version)

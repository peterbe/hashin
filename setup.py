from os import path
from setuptools import setup

_here = path.dirname(__file__)

# Prevent spurious errors during `python setup.py test`, a la
# http://www.eby-sarna.com/pipermail/peak/2010-May/003357.html:
try:
    import multiprocessing
    multiprocessing = multiprocessing  # take it easy pyflakes
except ImportError:
    pass

setup(
    name='hashin',
    version='0.12.0',
    description='Edits your requirements.txt by hashing them in',
    long_description=open(path.join(_here, 'README.rst')).read(),
    author='Peter Bengtsson',
    author_email='mail@peterbe.com',
    license='MIT',
    py_modules=['hashin'],
    entry_points={
        'console_scripts': ['hashin = hashin:main']
        },
    url='https://github.com/peterbe/hashin',
    include_package_data=True,
    tests_require=['nose>=1.3.0,<2.0', 'mock'],
    test_suite='nose.collector',
    classifiers=[
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Topic :: Software Development :: Build Tools',
        'Topic :: System :: Installation/Setup',
        'Topic :: System :: Systems Administration'
        ],
    keywords=['pip', 'repeatable', 'deploy', 'deployment', 'hash',
              'install', 'installer']
)

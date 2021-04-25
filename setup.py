import re
from setuptools import setup


def find_version():
    return re.search(r"^__version__ = '(.*)'$",
                     open('heatshrinkpy/version.py', 'r').read(),
                     re.MULTILINE).group(1)


setup(name='heatshrinkpy',
      version=find_version(),
      author='Antonis Kalou @ JOHAN Sports, Erik Moqvist, Marcin Jaworski',
      author_email='antonis@johan-sports.com, erik.moqvist@gmail.com, marcin@jaworski.me',
      description='Pure Python heatshrink library, based on heatshrink2 library',
      long_description=open('README.rst', 'r').read(),
      url='https://github.com/yawor/heatshrinkpy',
      license='ISC',
      classifiers=[
          'Programming Language :: Python :: 3'
      ],
      keywords='compression binding heatshrink LZSS pure',
      test_suite='tests',
      packages=['heatshrinkpy'])

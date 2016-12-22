from setuptools import setup

with open('requirements.txt') as file:
  dependencies = file.readlines()

setup(
  name='metaborg',
  version='0.1',
  description='MetaBorg release engineering scripts',
  url='https://github.com/metaborg/spoofax-releng',
  author='Gabriel Konat',
  author_email='g.d.p.konat@tudelft.nl',
  license='Apache 2.0',
  packages=['metaborg'],
  install_requires=dependencies
)

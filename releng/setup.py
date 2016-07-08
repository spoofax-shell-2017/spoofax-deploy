from setuptools import setup

setup(
  name='metaborg',
  version='0.1',
  description='MetaBorg release engineering scripts',
  url='https://github.com/metaborg/spoofax-releng',
  author='Gabriel Konat',
  author_email='g.d.p.konat@tudelft.nl',
  license='Apache 2.0',
  packages=['metaborg'],
  install_requires=['buildorchestra>=0.1.2', 'mavenpy>=0.1.2', 'gradlepy>=0.1.1', 'eclipsegen>=0.1.0']
)

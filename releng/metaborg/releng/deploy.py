import os
import shutil
from enum import unique, Enum

from buildorchestra.result import Artifact
from mavenpy.run import Maven


class DeployRepositories(object):
  def __init__(self, mavenIdentifier, mavenUrl, mavenIsSnapshot, bintrayRepoName):
    self.mavenIdentifier = mavenIdentifier
    self.mavenUrl = mavenUrl
    self.mavenIsSnapshot = mavenIsSnapshot
    self.bintrayRepoName = bintrayRepoName


@unique
class DeployKind(Enum):
  none = None
  snapshot = DeployRepositories('metaborg-nexus-snapshot',
    'http://artifacts.metaborg.org/content/repositories/snapshots/', True, None)
  release = DeployRepositories('bintray-metaborg-release',
    'https://api.bintray.com/maven/metaborg/maven-release/;publish=1', False, 'release')
  milestone = DeployRepositories('bintray-metaborg-milestone',
    'https://api.bintray.com/maven/metaborg/maven-milestone/;publish=1', False, 'milestone')

  @staticmethod
  def keys():
    return DeployKind.__members__.keys()

  @staticmethod
  def exists(kind):
    return kind in DeployKind.__members__.keys()


class MetaborgArtifact(Artifact):
  def __init__(self, name, package, version, location, target):
    super(MetaborgArtifact, self).__init__(name, location, target)
    self.package = package
    self.version = version



class MetaborgDeploy(object):
  @staticmethod
  def maven_local_deploy_path(rootPath):
    return os.path.join(rootPath, '.local-deploy-repository')

  @staticmethod
  def maven_local_deploy_properties(rootPath):
    path = MetaborgDeploy.maven_local_deploy_path(rootPath)
    return {
      'altDeploymentRepository': 'local::default::file:{}'.format(path)
    }

  @staticmethod
  def maven_local_file_deploy_properties(rootPath):
    path = MetaborgDeploy.maven_local_deploy_path(rootPath)
    return {
      'repositoryId': 'local',
      'url'         : 'file:{}'.format(path)
    }

  @staticmethod
  def maven_local_deploy_clean(rootPath):
    path = MetaborgDeploy.maven_local_deploy_path(rootPath)
    shutil.rmtree(path)

  @staticmethod
  def maven_remote_deploy(rootPath, repositoryId, repositoryUrl):
    path = MetaborgDeploy.maven_local_deploy_path(rootPath)
    maven = Maven()
    maven.properties = {
      'wagon.sourceId': 'local',
      'wagon.source'  : 'file:{}'.format(path),
      'wagon.targetId': repositoryId,
      'wagon.target'  : repositoryUrl,
    }
    maven.targets = ['org.codehaus.mojo:wagon-maven-plugin:1.0:merge-maven-repos']
    maven.run(rootPath, None)

  @staticmethod
  def artifact_remote_deploy(rootPath, repositoryUrl, artifact):
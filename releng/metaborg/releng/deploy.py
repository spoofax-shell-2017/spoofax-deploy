import os
import shutil
from enum import unique, Enum

from bintraypy.bintray import Bintray
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
  snapshot = DeployRepositories('metaborg-nexus',
    'http://artifacts.metaborg.org/content/repositories/snapshots/', True, None)
  release = DeployRepositories('metaborg-bintray',
    'https://api.bintray.com/maven/metaborg/maven/release/;publish=1', False, 'release')
  milestone = DeployRepositories('metaborg-bintray',
    'https://api.bintray.com/maven/metaborg/maven/milestone/;publish=1', False, 'milestone')

  @staticmethod
  def keys():
    return DeployKind.__members__.keys()

  @staticmethod
  def exists(kind):
    return kind in DeployKind.__members__.keys()


class MetaborgArtifact(Artifact):
  def __init__(self, name, package, location, target):
    super(MetaborgArtifact, self).__init__(name, location, target)
    self.package = package


class MetaborgDeploy(object):
  def __init__(self, rootPath, deployKind, bintrayUsername, bintrayKey, bintrayVersion):
    self.rootPath = rootPath
    self.deployKind = deployKind
    self.bintray = Bintray(bintrayUsername, bintrayKey)
    self.bintrayVersion = bintrayVersion

  def maven_local_deploy_path(self):
    return os.path.join(self.rootPath, '.local-deploy-repository')

  def maven_local_deploy_properties(self):
    path = self.maven_local_deploy_path()
    return {
      'altDeploymentRepository': '"local::default::file:{}"'.format(path)
    }

  def maven_local_file_deploy_properties(self):
    path = self.maven_local_deploy_path()
    return {
      'repositoryId': '"local"',
      'url'         : '"file:{}"'.format(path)
    }

  def maven_local_deploy_clean(self):
    path = self.maven_local_deploy_path()
    shutil.rmtree(path, ignore_errors=True)

  def maven_remote_deploy(self):
    path = MetaborgDeploy.maven_local_deploy_path(self.rootPath)
    maven = Maven()
    maven.properties = {
      'wagon.sourceId': '"local"',
      'wagon.source'  : '"file:{}"'.format(path),
      'wagon.targetId': '"{}"'.format(self.deployKind.mavenIdentifier),
      'wagon.target'  : '"{}"'.format(self.deployKind.mavenUrl),
    }
    maven.targets = ['org.codehaus.mojo:wagon-maven-plugin:1.0:merge-maven-repos']
    maven.run(self.rootPath, None)

  def artifact_remote_deploy(self, artifact):
    bintrayRepoName = self.deployKind.bintrayRepoName
    if not (self.bintrayVersion and bintrayRepoName and artifact.package):
      print("Skipping deployment of artifact '{}' to Bintray, it has no package name, no version was set, "
            "or no bintray repository was set".format(artifact.name))
      return
    self.bintray.upload_generic('metaborg', bintrayRepoName, artifact.package, self.bintrayVersion, artifact.target,
      publish=True)

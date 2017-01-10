import os
import shutil

from bintraypy.bintray import Bintray
from buildorchestra.result import FileArtifact
from mavenpy.run import Maven
from nexuspy.nexus import Nexus


class MetaborgFileArtifact(FileArtifact):
  def __init__(self, name, srcFile, dstFile, nexusMetadata=None, bintrayMetadata=None):
    super().__init__(name, srcFile, dstFile)
    self.nexusMetadata = nexusMetadata
    self.bintrayMetadata = bintrayMetadata


class MetaborgMavenDeployer(object):
  def __init__(self, rootPath, identifier, url, snapshot=True):
    self.rootPath = rootPath
    self.identifier = identifier
    self.url = url
    self.snapshot = snapshot

  def maven_local_deploy_path(self):
    return os.path.join(self.rootPath, '.local-deploy-repository')

  def maven_local_deploy_properties(self):
    path = self.maven_local_deploy_path()
    return {
      'altDeploymentRepository': '"local-deploy::default::file:{}"'.format(path),
      'deployRepositoryId'     : '"local-deploy"',
      'deployFileUrl'          : '"file:{}"'.format(path)
    }

  def maven_local_file_deploy_properties(self):
    path = self.maven_local_deploy_path()
    return {
      'repositoryId': '"local-deploy"',
      'url'         : '"file:{}"'.format(path)
    }

  def maven_local_deploy_clean(self):
    path = self.maven_local_deploy_path()
    shutil.rmtree(path, ignore_errors=True)

  def maven_remote_deploy(self):
    path = self.maven_local_deploy_path()
    maven = Maven()
    maven.properties = {
      'wagon.sourceId': '"local-deploy"',
      'wagon.source'  : '"file:{}"'.format(path),
      'wagon.targetId': '"{}"'.format(self.identifier),
      'wagon.target'  : '"{}"'.format(self.url),
    }
    maven.targets = ['org.codehaus.mojo:wagon-maven-plugin:1.0:merge-maven-repos']
    maven.run(self.rootPath, None)


class NexusMetadata(object):
  def __init__(self, groupId, artifactId, packaging=None, classifier=None):
    self.groupId = groupId
    self.artifactId = artifactId
    self.packaging = packaging
    self.classifier = classifier


class MetaborgNexusDeployer(object):
  def __init__(self, url, repository, version, username, password):
    self.repository = repository
    self.version = version
    self.nexus = Nexus(url, username, password)

  def artifact_remote_deploy(self, artifact):
    if not hasattr(artifact, 'nexusMetadata'):
      print("Skipping deployment of artifact '{}' to Nexus: no Nexus metadata was set".format(artifact.name))
      return
    metadata = artifact.nexusMetadata
    self.nexus.upload_artifact(artifact.srcFile, self.repository, metadata.groupId, metadata.artifactId, self.version,
      metadata.packaging, metadata.classifier)


class BintrayMetadata(object):
  def __init__(self, package):
    self.package = package


class MetaborgBintrayDeployer(object):
  def __init__(self, organization, repository, version, username, key):
    self.organization = organization
    self.repository = repository
    self.version = version
    self.bintray = Bintray(username, key)

  def artifact_remote_deploy(self, artifact):
    if not hasattr(artifact, 'bintrayMetadata'):
      print("Skipping deployment of artifact '{}' to Bintray: no Bintray metadata was set".format(artifact.name))
      return
    self.bintray.upload_generic(self.organization, self.repository, artifact.bintrayMetadata.package, self.version,
      artifact.srcFile, artifact.dstFile, publish=True)

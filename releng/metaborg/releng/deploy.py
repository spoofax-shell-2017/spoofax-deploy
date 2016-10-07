import os
import shutil

from bintraypy.bintray import Bintray
from buildorchestra.result import FileArtifact
from mavenpy.run import Maven


class MetaborgFileArtifact(FileArtifact):
  def __init__(self, name, package, srcFile, dstFile):
    super().__init__(name, srcFile, dstFile)
    self.package = package


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
      'altDeploymentRepository': '"local::default::file:{}"'.format(path),
      'deployRepositoryId'     : '"local"',
      'deployFileUrl'          : '"file:{}"'.format(path)
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
    path = self.maven_local_deploy_path()
    maven = Maven()
    maven.properties = {
      'wagon.sourceId': '"local"',
      'wagon.source'  : '"file:{}"'.format(path),
      'wagon.targetId': '"{}"'.format(self.identifier),
      'wagon.target'  : '"{}"'.format(self.url),
    }
    maven.targets = ['org.codehaus.mojo:wagon-maven-plugin:1.0:merge-maven-repos']
    maven.run(self.rootPath, None)


class MetaborgBintrayDeployer(object):
  def __init__(self, organization, repository, version, username, key):
    self.organization = organization
    self.repository = repository
    self.version = version
    self.bintray = Bintray(username, key)

  def artifact_remote_deploy(self, artifact):
    if not artifact.package:
      print("Skipping deployment of artifact '{}' to Bintray: no package name was set".format(artifact.name))
      return
    self.bintray.upload_generic(self.organization, self.repository, artifact.package, self.version, artifact.location,
      artifact.target, publish=True)

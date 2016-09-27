import os
import shutil

from bintraypy.bintray import Bintray
from buildorchestra.result import Artifact
from mavenpy.run import Maven


class MetaborgArtifact(Artifact):
  def __init__(self, name, package, location, target):
    super(MetaborgArtifact, self).__init__(name, location, target)
    self.package = package


class MetaborgMavenDeployer(object):
  def __init__(self, rootPath, identifier, url):
    self.rootPath = rootPath
    self.identifier = identifier
    self.url = url

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
    path = self.maven_local_deploy_path()
    maven = Maven()
    maven.properties = {
      'wagon.sourceId': '"local"',
      'wagon.source'  : '"file:{}"'.format(path),
      'wagon.targetId': '"{}"'.format(self.identifier),
      'wagon.target'  : '"{}"'.format(self.url),
    }
    maven.targets = ['org.codehaus.mojo:wagon-maven-plugin:1.0:merge-maven-repos']


class MetaborgBintrayDeployer(object):
  def __init__(self, organization, repository, version, username, key,):
    self.organization = organization
    self.repository = repository
    self.version = version
    self.bintray = Bintray(username, key)

  def artifact_remote_deploy(self, artifact):
    if not (self.organization and self.repository and artifact.package and self.version):
      print("Skipping deployment of artifact '{}' to Bintray: no organization, repository, package name, "
            "or version was set".format(artifact.name))
      return

    self.bintray.upload_generic(self.organization, self.repository, artifact.package, self.version, artifact.location,
      artifact.target, publish=True)

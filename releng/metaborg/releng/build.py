import glob
import os
import shutil

from buildorchestra.build import Builder
from buildorchestra.result import StepResult, Artifact
from gradlepy.run import Gradle
from mavenpy.run import Maven
from pyfiglet import Figlet

from eclipsegen.generate import Os, Arch
from metaborg.releng.deploy import MetaborgArtifact
from metaborg.releng.eclipse import MetaborgEclipseGenerator
from metaborg.util.git import create_qualifier


class RelengBuilder(object):
  def __init__(self, repo, buildDeps=True):
    self.__repo = repo

    self.clean = True

    self.skipTests = False

    self.offline = False

    self.debug = False
    self.quiet = False

    self.qualifier = None

    self.copyArtifactsTo = None

    self.generateJavaDoc = False

    self.buildStratego = False
    self.bootstrapStratego = False
    self.testStratego = True

    self.mavenSettingsFile = None
    self.mavenGlobalSettingsFile = None
    self.mavenCleanLocalRepo = False
    self.mavenLocalRepo = None
    self.mavenOpts = None

    self.mavenDeployer = None

    self.gradleNoNative = False
    self.gradleDaemon = None

    self.bintrayDeployer = None

    builder = Builder(copyOptions=True, dependencyAnalysis=buildDeps)
    self.__builder = builder

    # Main targets
    mainTargets = []

    def add_main_target(identifier, depIds, method):
      builder.add_build_step(identifier, depIds, method)
      mainTargets.append(identifier)
      return identifier

    poms = add_main_target('poms', [], RelengBuilder.__build_poms)
    jars = add_main_target('jars', [poms], RelengBuilder.__build_premade_jars)
    strategoxt = add_main_target('strategoxt', [poms, jars], RelengBuilder.__build_or_download_strategoxt)
    java = add_main_target('java', [poms, jars, strategoxt], RelengBuilder.__build_java)
    stdDeps = [poms, jars, strategoxt, java]
    add_main_target('java-uber', stdDeps + [], RelengBuilder.__build_java_uber)

    languagePrereq = add_main_target('language-prereqs', stdDeps + [], RelengBuilder.__build_language_prereqs)
    languages = add_main_target('languages', stdDeps + [languagePrereq], RelengBuilder.__build_languages)
    stdLangDeps = stdDeps + [languages]
    dynsem = add_main_target('dynsem', stdLangDeps, RelengBuilder.__build_dynsem)
    spt = add_main_target('spt', stdLangDeps, RelengBuilder.__build_spt)
    allLangDeps = stdLangDeps + [dynsem, spt]

    eclipsePrereqs = add_main_target('eclipse-prereqs', allLangDeps + [], RelengBuilder.__build_eclipse_prereqs)
    eclipse = add_main_target('eclipse', allLangDeps + [eclipsePrereqs], RelengBuilder.__build_eclipse)

    intellijPrereqs = add_main_target('intellij-prereqs', allLangDeps + [], RelengBuilder.__build_intellij_prereqs)
    intellijJps = add_main_target('intellij-jps', allLangDeps + [intellijPrereqs], RelengBuilder.__build_intellij_jps)
    add_main_target('intellij', allLangDeps + [intellijJps], RelengBuilder.__build_intellij)

    builder.add_target('all', mainTargets)

    # Additional targets
    builder.add_build_step('java-libs', [java], RelengBuilder.__build_java_libs)
    builder.add_build_step('eclipse-instances', [eclipse], RelengBuilder.__build_eclipse_instances)

  @property
  def targets(self):
    return self.__builder.all_steps_ordered

  def build(self, *targets):
    basedir = self.__repo.working_tree_dir

    if self.deployKind:
      deployer = MetaborgDeploy(basedir, self.deployKind, self.bintrayUsername, self.bintrayKey, self.bintrayVersion)
    else:
      deployer = None

    figlet = Figlet(width=200)

    buildStratego = self.buildStratego
    if self.bootstrapStratego:
      buildStratego = True

    qualifier = self.qualifier
    if not qualifier:
      qualifier = create_qualifier(self.__repo)
    print('Using Eclipse qualifier {}.'.format(qualifier))

    maven = Maven()
    maven.errors = True
    maven.batch = True
    # Disable annoying warnings when using Cygwin on Windows.
    maven.env['CYGWIN'] = 'nodosfilewarning'
    if self.clean:
      maven.targets.append('clean')
    maven.skipTests = self.skipTests
    maven.offline = self.offline
    maven.debug = self.debug
    maven.quiet = self.quiet
    if self.generateJavaDoc:
      maven.properties['generate-javadoc'] = True
    maven.settingsFile = self.mavenSettingsFile
    maven.globalSettingsFile = self.mavenGlobalSettingsFile
    if self.deployKind:
      # Always deploy locally first. If build succeeds, copy locally deployed artifacts to remote artifact server.
      deployer.maven_local_deploy_clean()
      maven.properties.update(deployer.maven_local_deploy_properties())
      if not self.deployKind.mavenIsSnapshot:
        maven.profiles.append('release')
    # Disable snapshot repositories for build isolation.
    maven.profiles.append('!add-metaborg-snapshot-repos')
    maven.profiles.append('!add-spoofax-eclipse-repos')
    maven.localRepo = self.mavenLocalRepo
    maven.opts = self.mavenOpts

    gradle = Gradle()
    gradle.stacktrace = True
    gradle.info = True
    gradle.offline = self.offline
    gradle.debug = self.debug
    gradle.quiet = self.quiet
    gradle.mavenLocalRepo = self.mavenLocalRepo
    gradle.noNative = self.gradleNoNative
    gradle.daemon = self.gradleDaemon

    if self.mavenCleanLocalRepo:
      print(figlet.renderText('Cleaning local maven repository'))
      # TODO: self.mavenLocalRepo can be None
      _clean_local_repo(self.mavenLocalRepo)

    print(figlet.renderText('Building'))
    result = self.__builder.build(
      *targets,
      basedir=basedir,
      deploy=self.deployKind is not None,
      deployer=deployer,
      skipTests=self.skipTests,
      qualifier=qualifier,
      buildStratego=buildStratego,
      bootstrapStratego=self.bootstrapStratego,
      testStratego=self.testStratego,
      maven=maven,
      gradle=gradle
    )

    if not result:
      return

    if self.deployKind:
      print(figlet.renderText('Deploying Maven artifacts'))
      deployer.maven_remote_deploy()
      if not (self.bintrayUsername and self.bintrayKey and self.bintrayVersion and self.deployKind.bintrayRepoName):
        print('Not deploying artifacts to Bintray: username, key, repository, or version was not set')
      else:
        print(figlet.renderText('Deploying other artifacts'))
        for artifact in result.artifacts:
          deployer.artifact_remote_deploy(artifact)

    if self.copyArtifactsTo:
      print(figlet.renderText('Copying other artifacts'))
      copyTo = _make_abs(self.copyArtifactsTo, self.__repo.working_tree_dir)
      result.copy_to(copyTo)

  # Builders

  @staticmethod
  def __build_poms(basedir, deploy, maven, **_):
    target = 'deploy' if deploy else 'install'
    cwd = os.path.join(basedir, 'releng', 'build', 'parent')
    maven.run_in_dir(cwd, target)

  @staticmethod
  def __build_premade_jars(basedir, deployer, maven, **_):
    cwd = os.path.join(basedir, 'releng', 'parent')

    # Install make-permissive
    makePermissivePath = os.path.join(basedir, 'jsglr', 'make-permissive', 'jar')
    makePermissivePom = os.path.join(makePermissivePath, 'pom.xml')
    makePermissiveJar = os.path.join(makePermissivePath, 'make-permissive.jar')

    if 'clean' in maven.targets:
      maven.targets.remove('clean')
    properties = {
      'pomFile': makePermissivePom,
      'file'   : makePermissiveJar,
    }
    maven.run_in_dir(cwd, 'install:install-file', **properties)
    if deployer:
      properties.update(deployer.maven_local_file_deploy_properties())
      maven.run_in_dir(cwd, 'deploy:deploy-file', **properties)

  @staticmethod
  def __build_or_download_strategoxt(buildStratego, **kwargs):
    if buildStratego:
      return RelengBuilder.__build_strategoxt(**kwargs)
    else:
      return RelengBuilder.__download_strategoxt(**kwargs)

  @staticmethod
  def __download_strategoxt(basedir, maven, **_):
    # Allow downloading from snapshot repositories when downloading StrategoXT.
    if '!add-metaborg-snapshot-repos' in maven.profiles:
      maven.profiles.remove('!add-metaborg-snapshot-repos')

    if 'clean' in maven.targets:
      maven.targets.remove('clean')

    cwd = os.path.join(basedir, 'strategoxt', 'strategoxt')
    maven.run(cwd, 'download-pom.xml', 'dependency:resolve')

  @staticmethod
  def __build_strategoxt(basedir, deploy, bootstrapStratego, testStratego, skipTests, maven, **_):
    target = 'deploy' if deploy else 'install'

    # Build StrategoXT
    if bootstrapStratego:
      buildFile = os.path.join('bootstrap-pom.xml')
    else:
      buildFile = os.path.join('build-pom.xml')
    properties = {'strategoxt-skip-test': skipTests or not testStratego}
    strategoXtDir = os.path.join(basedir, 'strategoxt', 'strategoxt')
    maven.run(strategoXtDir, buildFile, target, **properties)

    # Build StrategoXT parent POM
    properties = {'strategoxt-skip-build': True, 'strategoxt-skip-assembly': True}
    parentBuildFile = os.path.join('buildpoms', 'pom.xml')
    maven.run(strategoXtDir, parentBuildFile, target, **properties)

    if bootstrapStratego:
      distribDir = os.path.join(strategoXtDir, 'buildpoms', 'bootstrap3', 'target')
    else:
      distribDir = os.path.join(strategoXtDir, 'buildpoms', 'build', 'target')

    return StepResult([
      MetaborgArtifact('StrategoXT distribution', 'strategoxt-distrib',
        _glob_one('{}/strategoxt-distrib-*-bin.tar'.format(distribDir)),
        os.path.join('strategoxt', 'distrib.tar')),
      MetaborgArtifact('StrategoXT JAR', 'strategoxt-jar',
        '{}/dist/share/strategoxt/strategoxt/strategoxt.jar'.format(distribDir),
        os.path.join('strategoxt', 'strategoxt.jar')),
    ])

  @staticmethod
  def __build_java(basedir, qualifier, deploy, maven, **_):
    target = 'deploy' if deploy else 'install'
    cwd = os.path.join(basedir, 'releng', 'build', 'java')
    maven.run_in_dir(cwd, target, forceContextQualifier=qualifier)
    return StepResult([
      MetaborgArtifact('Spoofax sunshine JAR', 'spoofax-sunshine', _glob_one(
        os.path.join(basedir, 'spoofax-sunshine/org.metaborg.sunshine2/target/org.metaborg.sunshine2-*.jar')),
        os.path.join('spoofax', 'sunshine.jar')),
    ])

  @staticmethod
  def __build_java_uber(basedir, deploy, maven, **_):
    target = 'deploy' if deploy else 'install'
    cwd = os.path.join(basedir, 'spoofax', 'org.metaborg.spoofax.core.uber')
    maven.run_in_dir(cwd, target)
    return StepResult([
      MetaborgArtifact('Spoofax uber JAR', 'spoofax-core-uber',
        _glob_one(os.path.join(cwd, 'target/org.metaborg.spoofax.core.uber-*.jar')),
        os.path.join('spoofax', 'core-uber.jar')),
    ])

  @staticmethod
  def __build_java_libs(basedir, deploy, maven, **_):
    target = 'deploy' if deploy else 'install'
    cwd = os.path.join(basedir, 'releng', 'build', 'libs')
    maven.run_in_dir(cwd, target)
    return StepResult([
      Artifact('Spoofax libraries JAR',
        _glob_one(os.path.join(basedir, 'releng/build/libs/target/build.libs-*.jar')),
        os.path.join('spoofax', 'libs.jar')),
    ])

  @staticmethod
  def __build_language_prereqs(basedir, deploy, maven, **_):
    target = 'deploy' if deploy else 'install'
    cwd = os.path.join(basedir, 'releng', 'build', 'language', 'parent')
    maven.run_in_dir(cwd, target)

  @staticmethod
  def __build_languages(basedir, deploy, maven, **_):
    target = 'deploy' if deploy else 'install'
    cwd = os.path.join(basedir, 'releng', 'build', 'language')
    maven.run_in_dir(cwd, target)

  @staticmethod
  def __build_dynsem(basedir, deploy, maven, **_):
    target = 'deploy' if deploy else 'install'
    cwd = os.path.join(basedir, 'releng', 'build', 'language', 'dynsem')
    # Don't skip expensive steps, always clean, because of incompatibilities/bugs with annotation processor.
    if 'clean' not in maven.targets:
      maven.targets.insert(0, 'clean')
    maven.run_in_dir(cwd, target)

  @staticmethod
  def __build_spt(basedir, deploy, maven, **_):
    target = 'deploy' if deploy else 'install'
    cwd = os.path.join(basedir, 'releng', 'build', 'language', 'spt')
    maven.run_in_dir(cwd, target)
    return StepResult([
      MetaborgArtifact('SPT testrunner JAR', 'spoofax-testrunner',
        _glob_one(os.path.join(basedir, 'spt/org.metaborg.spt.cmd/target/org.metaborg.spt.cmd-*.jar')),
        os.path.join('spoofax', 'testrunner.jar')),
    ])

  @staticmethod
  def __build_eclipse_prereqs(basedir, qualifier, deploy, maven, **_):
    target = 'deploy' if deploy else 'install'
    cwd = os.path.join(basedir, 'releng', 'build', 'eclipse', 'deps')
    maven.run_in_dir(cwd, target, forceContextQualifier=qualifier)

  @staticmethod
  def __build_eclipse(basedir, qualifier, maven, **_):
    cwd = os.path.join(basedir, 'releng', 'build', 'eclipse')
    maven.run_in_dir(cwd, 'install', forceContextQualifier=qualifier)
    return StepResult([
      Artifact('Spoofax Eclipse update site',
        _glob_one(os.path.join(basedir, 'spoofax-eclipse/org.metaborg.spoofax.eclipse.updatesite/target/org.metaborg.spoofax.eclipse.updatesite-*.zip')),
        'spoofax-eclipse.zip'),
    ])

  @staticmethod
  def __build_eclipse_instances(basedir, **_):
    eclipsegenPath = 'eclipsegen'

    generator = MetaborgEclipseGenerator(basedir, eclipsegenPath, spoofax=True, spoofaxRepoLocal=True)
    archives = generator.generate_all(oss=Os.values(), archs=Arch.values(), fixIni=True, addJre=True,
      archiveJreSeparately=True, archivePrefix='spoofax')

    artifacts = []
    for archive in archives:
      location = archive.location
      target = os.path.join('spoofax', 'eclipse', os.path.basename(location))
      artifacts.append(MetaborgArtifact('Spoofax Eclipse instance', 'spoofax-eclipse-installation', location, target))
    return StepResult(artifacts)

  @staticmethod
  def __build_intellij_prereqs(basedir, gradle, **_):
    target = 'publishToMavenLocal'  # TODO: Deploy
    cwd = os.path.join(basedir, 'spoofax-intellij', 'org.metaborg.jps-deps')
    gradle.run_in_dir(cwd, target)

  @staticmethod
  def __build_intellij_jps(basedir, gradle, **_):
    target = 'install'  # TODO: Deploy
    cwd = os.path.join(basedir, 'spoofax-intellij', 'org.metaborg.jps')
    gradle.run_in_dir(cwd, target)

  @staticmethod
  def __build_intellij(basedir, gradle, **_):
    target = 'buildPlugin'  # TODO: Deploy
    cwd = os.path.join(basedir, 'spoofax-intellij', 'org.metaborg.intellij')
    gradle.run_in_dir(cwd, target)
    return StepResult([
      MetaborgArtifact('Spoofax for IntelliJ IDEA plugin',
        _glob_one(os.path.join(basedir,
          'spoofax-intellij/org.metaborg.intellij/build/distributions/org.metaborg.intellij-*.zip')),
        os.path.join('spoofax', 'intellij', 'plugin.zip')),
    ])


# Private helper functions

def _glob_one(path):
  globs = glob.glob(path)
  if not globs:
    raise RuntimeError('Could not find path with pattern {}'.format(path))
  return globs[0]


def _clean_local_repo(localRepo):
  print('Cleaning artifacts from local repository')
  metaborgPath = os.path.join(localRepo, 'org', 'metaborg')
  print('Deleting {}'.format(metaborgPath))
  shutil.rmtree(metaborgPath, ignore_errors=True)
  cachePath = os.path.join(localRepo, '.cache', 'tycho')
  print('Deleting {}'.format(cachePath))
  shutil.rmtree(cachePath, ignore_errors=True)


def _make_abs(directory, relativeTo):
  if not os.path.isabs(directory):
    return os.path.normpath(os.path.join(relativeTo, directory))
  return directory

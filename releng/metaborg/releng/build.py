import glob
import os
import shutil

from buildorchestra.build import Builder
from buildorchestra.result import StepResult, FileArtifact, DirArtifact
from eclipsegen.generate import Os, Arch
from gradlepy.run import Gradle
from mavenpy.run import Maven
from pyfiglet import Figlet

from metaborg.releng.deploy import MetaborgFileArtifact, BintrayMetadata, NexusMetadata
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
    self.copyArtifactsTo = None
    self.generateJavaDoc = False

    self.buildStratego = False
    self.bootstrapStratego = False
    self.testStratego = True

    self.eclipseQualifier = None
    self.eclipseGenMoreRepos = []
    self.eclipseGenMoreIUs = []

    self.mavenSettingsFile = None
    self.mavenGlobalSettingsFile = None
    self.mavenCleanLocalRepo = False
    self.mavenLocalRepo = None
    self.mavenOpts = None

    self.mavenDeployer = None

    self.gradleNative = False
    self.gradleDaemon = None

    self.nexusDeployer = None
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

    intellij = add_main_target('intellij', allLangDeps, RelengBuilder.__build_intellij)
    spt_intellij = add_main_target('spt-intellij', [spt], RelengBuilder.__build_spt_intellij)

    builder.add_target('all', mainTargets)

    # Additional targets
    builder.add_build_step('java-libs', [java], RelengBuilder.__build_java_libs)
    builder.add_build_step('eclipse-instances', [eclipse], RelengBuilder.__build_eclipse_instances)

  @property
  def targets(self):
    return self.__builder.all_steps_ordered

  def build(self, *targets):
    basedir = self.__repo.working_tree_dir

    figlet = Figlet(width=200)

    buildStratego = self.buildStratego
    if self.bootstrapStratego:
      buildStratego = True

    qualifier = self.eclipseQualifier
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
    if self.mavenDeployer:
      # Always deploy locally first. If build succeeds, copy locally deployed artifacts to remote artifact server.
      self.mavenDeployer.maven_local_deploy_clean()
      maven.properties.update(self.mavenDeployer.maven_local_deploy_properties())
      if not self.mavenDeployer.snapshot:
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
    gradle.noNative = not self.gradleNative
    gradle.daemon = self.gradleDaemon

    # TODO: clean standard local repo (~/.m2/repository) when self.mavenLocalRepo is None
    if self.mavenCleanLocalRepo and self.mavenLocalRepo:
      print(figlet.renderText('Cleaning local maven repository'))
      _clean_local_repo(self.mavenLocalRepo)

    print(figlet.renderText('Building'))
    result = self.__builder.build(
      *targets,
      basedir=basedir,
      skipTests=self.skipTests,
      eclipseQualifier=qualifier,
      eclipseGenMoreRepos=self.eclipseGenMoreRepos,
      eclipseGenMoreIUs=self.eclipseGenMoreIUs,
      buildStratego=buildStratego,
      bootstrapStratego=self.bootstrapStratego,
      testStratego=self.testStratego,
      maven=maven,
      mavenDeployer=self.mavenDeployer,
      gradle=gradle,
      bintrayDeployer=self.bintrayDeployer
    )

    if not result:
      return

    if self.mavenDeployer:
      print(figlet.renderText('Deploying Maven artifacts'))
      self.mavenDeployer.maven_remote_deploy()

    if self.nexusDeployer:
      print(figlet.renderText('Deploying artifacts to Nexus'))
      for artifact in result.artifacts:
        self.nexusDeployer.artifact_remote_deploy(artifact)

    if self.bintrayDeployer:
      print(figlet.renderText('Deploying artifacts to Bintray'))
      for artifact in result.artifacts:
        self.bintrayDeployer.artifact_remote_deploy(artifact)

    if self.copyArtifactsTo:
      print(figlet.renderText('Copying other artifacts'))
      copyTo = _make_abs(self.copyArtifactsTo, self.__repo.working_tree_dir)
      result.copy_to(copyTo)

  # Builders

  @staticmethod
  def __build_poms(basedir, maven, mavenDeployer, **_):
    target = 'deploy' if mavenDeployer else 'install'
    cwd = os.path.join(basedir, 'releng', 'build', 'parent')
    maven.run_in_dir(cwd, target)

  @staticmethod
  def __build_premade_jars(basedir, maven, mavenDeployer, **_):
    cwd = os.path.join(basedir, 'releng', 'parent')

    # Install and deploy make-permissive
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
    if mavenDeployer:
      properties.update(mavenDeployer.maven_local_file_deploy_properties())
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
  def __build_strategoxt(basedir, bootstrapStratego, testStratego, skipTests, eclipseQualifier, maven, mavenDeployer, **_):
    target = 'deploy' if mavenDeployer else 'install'

    # Build StrategoXT
    if bootstrapStratego:
      buildFile = os.path.join('bootstrap-pom.xml')
    else:
      buildFile = os.path.join('build-pom.xml')
    properties = {'strategoxt-skip-test': skipTests or not testStratego, 'forceContextQualifier': eclipseQualifier}
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
      FileArtifact(
        'StrategoXT distribution',
        _glob_one('{}/strategoxt-distrib-*-bin.tar'.format(distribDir)),
        os.path.join('strategoxt', 'distrib.tar')
      ),
      FileArtifact(
        'StrategoXT JAR',
        '{}/dist/share/strategoxt/strategoxt/strategoxt.jar'.format(distribDir),
        os.path.join('strategoxt', 'strategoxt.jar')
      ),
    ])

  @staticmethod
  def __build_java(basedir, eclipseQualifier, maven, mavenDeployer, **_):
    target = 'deploy' if mavenDeployer else 'install'
    cwd = os.path.join(basedir, 'releng', 'build', 'java')
    maven.run_in_dir(cwd, target, forceContextQualifier=eclipseQualifier)
    return StepResult([
      FileArtifact(
        'Spoofax sunshine JAR',
        _glob_one(os.path.join(basedir, 'spoofax-sunshine/org.metaborg.sunshine2/target/org.metaborg.sunshine2-*.jar'))
      )
    ])

  @staticmethod
  def __build_java_uber(basedir, eclipseQualifier, maven, mavenDeployer, **_):
    target = 'deploy' if mavenDeployer else 'install'
    cwd = os.path.join(basedir, 'spoofax', 'org.metaborg.spoofax.core.uber')
    maven.run_in_dir(cwd, target, forceContextQualifier=eclipseQualifier)
    return StepResult([
      FileArtifact(
        'Spoofax uber JAR',
        _glob_one(os.path.join(cwd, 'target/org.metaborg.spoofax.core.uber-*.jar'))
      )
    ])

  @staticmethod
  def __build_java_libs(basedir, eclipseQualifier, maven, mavenDeployer, **_):
    target = 'deploy' if mavenDeployer else 'install'
    cwd = os.path.join(basedir, 'releng', 'build', 'libs')
    maven.run_in_dir(cwd, target, forceContextQualifier=eclipseQualifier)
    return StepResult([
      FileArtifact(
        'Spoofax libraries JAR',
        _glob_one(os.path.join(basedir, 'releng/build/libs/target/build.libs-*.jar'))
      )
    ])

  @staticmethod
  def __build_language_prereqs(basedir, maven, mavenDeployer, **_):
    target = 'deploy' if mavenDeployer else 'install'
    cwd = os.path.join(basedir, 'releng', 'build', 'language', 'parent')
    maven.run_in_dir(cwd, target)

  @staticmethod
  def __build_languages(basedir, maven, mavenDeployer, **_):
    target = 'deploy' if mavenDeployer else 'install'
    cwd = os.path.join(basedir, 'releng', 'build', 'language')
    maven.run_in_dir(cwd, target)

  @staticmethod
  def __build_dynsem(basedir, eclipseQualifier, maven, mavenDeployer, **_):
    target = 'deploy' if mavenDeployer else 'install'
    cwd = os.path.join(basedir, 'releng', 'build', 'language', 'dynsem')
    # Don't skip expensive steps, always clean, because of incompatibilities/bugs with annotation processor.
    if 'clean' not in maven.targets:
      maven.targets.insert(0, 'clean')
    maven.run_in_dir(cwd, target, forceContextQualifier=eclipseQualifier)

  @staticmethod
  def __build_spt(basedir, eclipseQualifier, maven, mavenDeployer, **_):
    target = 'deploy' if mavenDeployer else 'install'
    cwd = os.path.join(basedir, 'releng', 'build', 'language', 'spt')
    maven.run_in_dir(cwd, target, forceContextQualifier=eclipseQualifier)
    return StepResult([
      FileArtifact(
        'SPT testrunner JAR',
        _glob_one(os.path.join(basedir, 'spt/org.metaborg.spt.cmd/target/org.metaborg.spt.cmd-*.jar'))
      )
    ])

  @staticmethod
  def __build_eclipse_prereqs(basedir, eclipseQualifier, maven, mavenDeployer, **_):
    target = 'deploy' if mavenDeployer else 'install'
    cwd = os.path.join(basedir, 'releng', 'build', 'eclipse', 'deps')
    maven.run_in_dir(cwd, target, forceContextQualifier=eclipseQualifier)

  @staticmethod
  def __build_eclipse(basedir, eclipseQualifier, maven, mavenDeployer, **_):
    target = 'deploy' if mavenDeployer else 'install'
    cwd = os.path.join(basedir, 'releng', 'build', 'eclipse')
    maven.run_in_dir(cwd, target, forceContextQualifier=eclipseQualifier)
    return StepResult([
      DirArtifact(
        'Spoofax Eclipse update site',
        _glob_one(os.path.join(basedir, 'spoofax-eclipse/org.metaborg.spoofax.eclipse.updatesite/target/site')),
        os.path.join('spoofax', 'eclipse', 'site')
      )
    ])

  @staticmethod
  def __build_eclipse_instances(basedir, eclipseGenMoreRepos, eclipseGenMoreIUs, **_):
    eclipsegenPath = '.eclipsegen'

    generator = MetaborgEclipseGenerator(basedir, eclipsegenPath, spoofax=True, spoofaxRepoLocal=True,
      moreRepos=eclipseGenMoreRepos, moreIUs=eclipseGenMoreIUs)
    archives = generator.generate_all(oss=Os.values(), archs=Arch.values(), fixIni=True, addJre=True,
      archiveJreSeparately=True, name='spoofax', archivePrefix='spoofax')

    artifacts = []
    for archive in archives:
      location = archive.location
      target = os.path.join('spoofax', 'eclipse', os.path.basename(location))
      packaging = 'zip' if archive.os.archiveFormat == 'zip' else 'tar.gz'
      classifier = '{}-{}{}'.format(archive.os.name, archive.arch.name, '-jre' if archive.withJre else '')
      artifacts.append(MetaborgFileArtifact(
        'Spoofax Eclipse instance',
        location,
        target,
        NexusMetadata('org.metaborg', 'org.metaborg.spoofax.eclipse.dist', packaging, classifier),
      ))
    return StepResult(artifacts)

  @staticmethod
  def __build_intellij(basedir, gradle, **_):
    target = 'install'
    cwd = os.path.join(basedir, 'spoofax-intellij', 'org.metaborg.intellij')
    gradle.run_in_dir(cwd, target)
    return StepResult([
      MetaborgFileArtifact(
        'Spoofax for IntelliJ IDEA plugin',
        _glob_one(os.path.join(basedir,
          'spoofax-intellij/org.metaborg.intellij/build/distributions/org.metaborg.intellij-*.zip')),
        os.path.join('spoofax', 'intellij', 'plugin.zip'),
        NexusMetadata('org.metaborg', 'org.metaborg.intellij.dist'),
        BintrayMetadata('spoofax-intellij-updatesite')
      ),
    ])

  @staticmethod
  def __build_spt_intellij(basedir, gradle, **_):
    target = 'install'
    cwd = os.path.join(basedir, 'spt', 'org.metaborg.spt.testrunner.intellij')
    gradle.run_in_dir(cwd, target)
    return StepResult([
      MetaborgFileArtifact(
        'SPT test runner for IntelliJ',
        _glob_one(os.path.join(basedir, cwd, 'build', 'distributions', 'org.metaborg.spt.testrunner.intellij-*.zip')),
        os.path.join('spt', 'intellij', 'plugin.zip'),
        NexusMetadata('org.metaborg', 'org.metaborg.spt.testrunner.intellij'),
        BintrayMetadata('spt-intellij-updatesite')
      ),
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

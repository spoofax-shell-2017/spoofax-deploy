import glob
import os
import shutil

from gradlepy.run import Gradle

from mavenpy.run import Maven

from eclipsegen.generate import EclipseConfiguration
from buildorchestra.build import Builder
from buildorchestra.result import StepResult, Artifact
from metaborg.releng.eclipse import MetaborgEclipseGenerator
from metaborg.util.git import create_qualifier


class RelengBuilder(object):
  def __init__(self, repo, buildDeps=True):
    self.__repo = repo

    self.copyArtifactsTo = None

    self.clean = True
    self.deploy = False
    self.release = False

    self.skipTests = False
    self.skipExpensive = False

    self.offline = False

    self.debug = False
    self.quiet = False

    self.qualifier = None

    self.generateJavaDoc = False

    self.buildStratego = False
    self.bootstrapStratego = False
    self.testStratego = True

    self.mavenSettingsFile = None
    self.mavenGlobalSettingsFile = None
    self.mavenCleanLocalRepo = False
    self.mavenLocalRepo = None
    self.mavenOpts = None

    self.gradleNoNative = False

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
    add_main_target('intellij', allLangDeps + [intellijPrereqs], RelengBuilder.__build_intellij)

    builder.add_target('all', mainTargets)

    # Additional targets
    builder.add_build_step('java-libs', [java], RelengBuilder.__build_java_libs)
    builder.add_build_step('eclipse-instances', [eclipse], RelengBuilder.__build_eclipse_instances)

  @property
  def targets(self):
    return self.__builder.all_steps_ordered

  def build(self, *targets):
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
    if self.release:
      maven.profiles.append('release')
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
    # Disable the Gradle daemon; it causes issues on the build farm?
    # FIXME: Make this an option `gradle.daemon = False` in gradlepy.
    gradle.env['GRADLE_OPTS'] = '-Dorg.gradle.daemon=false'

    if self.mavenCleanLocalRepo:
      # TODO: self.mavenLocalRepo can be None
      _clean_local_repo(self.mavenLocalRepo)

    result = self.__builder.build(
      *targets,
      basedir=self.__repo.working_tree_dir,
      deploy=self.deploy,
      release=self.release,
      skipTests=self.skipTests,
      skipExpensive=self.skipExpensive,
      qualifier=qualifier,
      buildStratego=buildStratego,
      bootstrapStratego=self.bootstrapStratego,
      testStratego=self.testStratego,
      maven=maven,
      gradle=gradle
    )
    if self.copyArtifactsTo:
      copyTo = _make_abs(self.copyArtifactsTo, self.__repo.working_tree_dir)
      result.copy_to(copyTo)

  # Builders

  @staticmethod
  def __build_poms(basedir, deploy, maven, **_):
    target = 'deploy' if deploy else 'install'
    cwd = os.path.join(basedir, 'releng', 'build', 'parent')
    maven.run_in_dir(cwd, target)

  @staticmethod
  def __build_premade_jars(basedir, deploy, release, maven, **_):
    target = 'deploy:deploy-file' if deploy else 'install:install-file'

    cwd = os.path.join(basedir, 'releng', 'parent')

    # Install make-permissive
    makePermissivePath = os.path.join(basedir, 'jsglr', 'make-permissive', 'jar')
    makePermissivePom = os.path.join(makePermissivePath, 'pom.xml')
    makePermissiveJar = os.path.join(makePermissivePath, 'make-permissive.jar')

    repositoryId = "metaborg-nexus"
    if release:
      deployUrl = 'http://artifacts.metaborg.org/content/repositories/releases/'
    else:
      deployUrl = 'http://artifacts.metaborg.org/content/repositories/snapshots/'

    if 'clean' in maven.targets:
      maven.targets.remove('clean')
    properties = {'pomFile': makePermissivePom,
      'file'               : makePermissiveJar,
      'repositoryId'       : repositoryId,
      'url'                : deployUrl
    }
    maven.run_in_dir(cwd, target, **properties)

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
  def __build_strategoxt(basedir, deploy, bootstrapStratego, testStratego, skipTests, skipExpensive, maven, **_):
    target = 'deploy' if deploy else 'install'

    # Build StrategoXT
    if bootstrapStratego:
      buildFile = os.path.join('bootstrap-pom.xml')
    else:
      buildFile = os.path.join('build-pom.xml')
    if skipExpensive:
      properties = {'strategoxt-skip-build': True, 'strategoxt-skip-test': True}
    else:
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
      Artifact('StrategoXT distribution', _glob_one('{}/strategoxt-distrib-*-bin.tar'.format(distribDir)),
        'strategoxt-distrib.tar'),
      Artifact('StrategoXT JAR', '{}/dist/share/strategoxt/strategoxt/strategoxt.jar'.format(distribDir),
        'strategoxt.jar'),
      Artifact('StrategoXT minified JAR',
        _glob_one('{}/buildpoms/minjar/target/strategoxt-min-jar-*.jar'.format(strategoXtDir)),
        'strategoxt-min.jar'),
    ])

  @staticmethod
  def __build_java(basedir, qualifier, deploy, maven, **_):
    target = 'deploy' if deploy else 'install'
    cwd = os.path.join(basedir, 'releng', 'build', 'java')
    maven.run_in_dir(cwd, target, forceContextQualifier=qualifier)
    return StepResult([
      Artifact('Spoofax sunshine JAR', _glob_one(
        os.path.join(basedir, 'spoofax-sunshine/org.metaborg.sunshine2/target/org.metaborg.sunshine2-*.jar')),
        'spoofax-sunshine.jar'),
    ])

  @staticmethod
  def __build_java_uber(basedir, deploy, maven, **_):
    target = 'deploy' if deploy else 'install'
    cwd = os.path.join(basedir, 'spoofax', 'org.metaborg.spoofax.core.uber')
    maven.run_in_dir(cwd, target)
    return StepResult([
      Artifact('Spoofax uber JAR', _glob_one(os.path.join(cwd, 'target/org.metaborg.spoofax.core.uber-*.jar')),
        'spoofax-uber.jar'),
    ])

  @staticmethod
  def __build_java_libs(basedir, deploy, maven, **_):
    target = 'deploy' if deploy else 'install'
    cwd = os.path.join(basedir, 'releng', 'build', 'libs')
    maven.run_in_dir(cwd, target)
    return StepResult([
      Artifact('Spoofax libraries JAR', _glob_one(os.path.join(basedir, 'releng/build/libs/target/build.libs-*.jar')),
        'spoofax-libs.jar'),
    ])

  @staticmethod
  def __build_language_prereqs(basedir, deploy, maven, **_):
    target = 'deploy' if deploy else 'install'
    cwd = os.path.join(basedir, 'releng', 'build', 'language', 'parent')
    maven.run_in_dir(cwd, target)

  @staticmethod
  def __build_languages(basedir, deploy, skipExpensive, maven, **_):
    target = 'deploy' if deploy else 'install'
    properties = {'spoofax.skip': True} if skipExpensive else {}
    cwd = os.path.join(basedir, 'releng', 'build', 'language')
    maven.run_in_dir(cwd, target, **properties)

  @staticmethod
  def __build_dynsem(basedir, deploy, maven, **_):
    target = 'deploy' if deploy else 'install'
    cwd = os.path.join(basedir, 'releng', 'build', 'language', 'dynsem')
    # Don't skip expensive steps, always clean, because of incompatibilities/bugs with annotation processor.
    if 'clean' not in maven.targets:
      maven.targets.insert(0, 'clean')
    maven.run_in_dir(cwd, target)

  @staticmethod
  def __build_spt(basedir, deploy, skipExpensive, maven, **_):
    target = 'deploy' if deploy else 'install'
    properties = {'spoofax.skip': True} if skipExpensive else {}
    cwd = os.path.join(basedir, 'releng', 'build', 'language', 'spt')
    maven.run_in_dir(cwd, target, **properties)
    return StepResult([
      Artifact('SPT testrunner JAR', _glob_one(os.path.join(basedir,
        'spt/org.metaborg.spt.cmd/target/org.metaborg.spt.cmd-*.jar')), 'spoofax-testrunner.jar'),
    ])

  @staticmethod
  def __build_eclipse_prereqs(basedir, qualifier, deploy, maven, **_):
    target = 'deploy' if deploy else 'install'
    cwd = os.path.join(basedir, 'releng', 'build', 'eclipse', 'deps')
    maven.run_in_dir(cwd, target, forceContextQualifier=qualifier)

  @staticmethod
  def __build_eclipse(basedir, qualifier, deploy, maven, **_):
    target = 'deploy' if deploy else 'install'
    cwd = os.path.join(basedir, 'releng', 'build', 'eclipse')
    maven.run_in_dir(cwd, target, forceContextQualifier=qualifier)
    return StepResult([
      Artifact('Spoofax Eclipse update site', os.path.join(basedir,
        'spoofax-eclipse/org.metaborg.spoofax.eclipse.updatesite/target/site_assembly.zip'),
        'spoofax-eclipse.zip'),
    ])

  @staticmethod
  def __build_eclipse_instances(basedir, **_):
    eclipsegenPath = 'eclipsegen'

    def generate(eclipseOs, eclipseArch):
      generator = MetaborgEclipseGenerator(basedir, eclipsegenPath,
        EclipseConfiguration(os=eclipseOs, arch=eclipseArch), spoofax=True, spoofaxRepoLocal=True, archive=True)
      generator.generate(fixIni=True, addJre=True, archiveJreSeparately=True, archivePrefix='spoofax')

    generate('win32', 'x86')
    generate('win32', 'x86_64')
    generate('linux', 'x86')
    generate('linux', 'x86_64')
    generate('macosx', 'x86_64')

    archives = glob.glob(os.path.join(basedir, eclipsegenPath, '*'))
    artifacts = []
    for archive in archives:
      targetName = os.path.join('eclipse', os.path.basename(archive))
      artifacts.append(Artifact('Spoofax Eclipse instance', archive, targetName))
    return StepResult(artifacts)

  @staticmethod
  def __build_intellij_prereqs(basedir, gradle, **_):
    target = 'publishToMavenLocal'  # TODO: Deploy
    cwd = os.path.join(basedir, 'spoofax-intellij', 'org.metaborg.intellij', 'deps')
    gradle.run_in_dir(cwd, target)

  @staticmethod
  def __build_intellij(basedir, gradle, **_):
    target = 'buildPlugin'  # TODO: Deploy
    cwd = os.path.join(basedir, 'spoofax-intellij', 'org.metaborg.intellij')
    gradle.run_in_dir(cwd, target)
    return StepResult([
      Artifact('Spoofax for IntelliJ IDEA plugin',
        _glob_one(os.path.join(basedir,
          'spoofax-intellij/org.metaborg.intellij/build/distributions/org.metaborg.intellij-*.zip')),
        'spoofax-intellij.zip'),
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

import os
from os import path

from git.repo.base import Repo
from plumbum import cli

from eclipsegen.generate import Os, Arch
from metaborg.releng.bootstrap import Bootstrap
from metaborg.releng.build import RelengBuilder
from metaborg.releng.deploy import DeployKind
from metaborg.releng.eclipse import MetaborgEclipseGenerator
from metaborg.releng.icon import GenerateIcons
from metaborg.releng.maven import MetaborgMavenSettingsGeneratorGenerator
from metaborg.releng.release import MetaborgRelease
from metaborg.releng.versions import SetVersions
from metaborg.util.git import (CheckoutAll, CleanAll, MergeAll, PushAll,
  RemoteType, ResetAll, SetRemoteAll, TagAll,
  TrackAll, UpdateAll, create_now_qualifier, create_qualifier, repo_changed)
from metaborg.util.path import CommonPrefix
from metaborg.util.prompt import YesNo, YesNoTrice, YesNoTwice


class MetaborgReleng(cli.Application):
  PROGNAME = 'b'

  repoDirectory = '.'
  repo = None

  @cli.switch(names=["--repo", "-r"], argtype=str)
  def repo_directory(self, directory):
    """
    Sets the spoofax-releng repository to operate on.
    Defaults to the current directory if not set
    """
    self.repoDirectory = directory

  def main(self):
    if not self.nested_command:
      print('Error: no command given')
      self.help()
      return 1
    cli.ExistingDirectory(self.repoDirectory)

    self.repo = Repo(self.repoDirectory)
    return 0


@MetaborgReleng.subcommand("update")
class MetaborgRelengUpdate(cli.Application):
  """
  Updates all submodules to the latest commit on the remote repository
  """

  depth = cli.SwitchAttr(names=['-d', '--depth'], default=None, argtype=int, mandatory=False,
    help='Depth to update with')

  def main(self):
    print('Updating all submodules')
    UpdateAll(self.parent.repo, depth=self.depth)
    return 0


@MetaborgReleng.subcommand("set-remote")
class MetaborgRelengSetRemote(cli.Application):
  """
  Changes the remote for all submodules to an SSH or HTTP remote.
  """

  toSsh = cli.Flag(names=['-s', '--ssh'], default=False, excludes=['--http'], help='Set remotes to SSH remotes')
  toHttp = cli.Flag(names=['-h', '--http'], default=False, excludes=['--ssh'],
    help='Set remotes to HTTP remotes')

  def main(self):
    if not self.toSsh and not self.toHttp:
      print('Must choose between SSH (-s) or HTTP (-h)')
      return 1

    if self.toSsh:
      toType = RemoteType.SSH
    elif self.toHttp:
      toType = RemoteType.HTTP

    print('Setting remotes for all submodules')
    # noinspection PyUnboundLocalVariable
    SetRemoteAll(self.parent.repo, toType=toType)
    return 0


@MetaborgReleng.subcommand("clean-update")
class MetaborgRelengCleanUpdate(cli.Application):
  """
  Resets, cleans, and updates all submodules to the latest commit on the remote repository
  """

  confirmPrompt = cli.Flag(names=['-y', '--yes'], default=False,
    help='Answer warning prompts with yes automatically')

  depth = cli.SwitchAttr(names=['-d', '--depth'], default=None, argtype=int, mandatory=False,
    help='Depth to update with')

  def main(self):
    if not self.confirmPrompt:
      print(
        'WARNING: This will DELETE UNCOMMITED CHANGES, DELETE UNPUSHED COMMITS, and DELETE UNTRACKED FILES. Do you '
        'want to continue?')
      if not YesNoTrice():
        return 1
    print('Resetting, cleaning, and updating all submodules')
    repo = self.parent.repo
    CheckoutAll(repo)
    ResetAll(repo, toRemote=True)
    CheckoutAll(repo)
    CleanAll(repo)
    UpdateAll(repo, depth=self.depth)
    return 0


@MetaborgReleng.subcommand("track")
class MetaborgRelengTrack(cli.Application):
  """
  Sets tracking branch to submodule remote branch for each submodule
  """

  def main(self):
    print('Setting tracking branch for each submodule')
    TrackAll(self.parent.repo)
    return 0


@MetaborgReleng.subcommand("merge")
class MetaborgRelengMerge(cli.Application):
  """
  Merges a branch into the current branch for each submodule
  """

  branch = cli.SwitchAttr(names=['-b', '--branch'], argtype=str, mandatory=True,
    help='Branch to merge')

  confirmPrompt = cli.Flag(names=['-y', '--yes'], default=False,
    help='Answer warning prompts with yes automatically')

  def main(self):
    print('Merging branch into current branch for each submodule')
    if not self.confirmPrompt:
      print('This will merge branches, changing the state of your repositories, do you want to continue?')
      if not YesNo():
        return 1
    MergeAll(self.parent.repo, self.branch)
    return 0


@MetaborgReleng.subcommand("tag")
class MetaborgRelengTag(cli.Application):
  """
  Creates a tag in each submodule
  """

  tag = cli.SwitchAttr(names=['-n', '--name'], argtype=str, mandatory=True,
    help='Name of the tag')
  description = cli.SwitchAttr(names=['-d', '--description'], argtype=str, mandatory=False, default=None,
    help='Description of the tag')

  confirmPrompt = cli.Flag(names=['-y', '--yes'], default=False,
    help='Answer warning prompts with yes automatically')

  def main(self):
    print('Creating a tag in each submodules')
    if not self.confirmPrompt:
      print('This creates tags, changing the state of your repositories, do you want to continue?')
      if not YesNo():
        return 1
    TagAll(self.parent.repo, self.tag, self.description)
    return 0


@MetaborgReleng.subcommand("push")
class MetaborgRelengPush(cli.Application):
  """
  Pushes the current branch for each submodule
  """

  confirmPrompt = cli.Flag(names=['-y', '--yes'], default=False,
    help='Answer warning prompts with yes automatically')

  def main(self):
    print('Pushing current branch for each submodule')
    if not self.confirmPrompt:
      print('This pushes commits to the remote repository, do you want to continue?')
      if not YesNo():
        return 1
    PushAll(self.parent.repo)
    return 0


@MetaborgReleng.subcommand("checkout")
class MetaborgRelengCheckout(cli.Application):
  """
  Checks out the correct branches for each submodule
  """

  confirmPrompt = cli.Flag(names=['-y', '--yes'], default=False,
    help='Answer warning prompts with yes automatically')

  def main(self):
    print('Checking out correct branches for all submodules')
    if not self.confirmPrompt:
      print(
        'WARNING: This will get rid of detached heads, including any commits you have made to detached heads, '
        'do you want to continue?')
      if not YesNo():
        return 1
    CheckoutAll(self.parent.repo)
    return 0


@MetaborgReleng.subcommand("clean")
class MetaborgRelengClean(cli.Application):
  """
  Cleans untracked files in each submodule
  """

  confirmPrompt = cli.Flag(names=['-y', '--yes'], default=False,
    help='Answer warning prompts with yes automatically')

  def main(self):
    print('Cleaning all submodules')
    if not self.confirmPrompt:
      print('WARNING: This will DELETE UNTRACKED FILES, do you want to continue?')
      if not YesNoTwice():
        return 1
    CleanAll(self.parent.repo)
    return 0


@MetaborgReleng.subcommand("reset")
class MetaborgRelengReset(cli.Application):
  """
  Resets each submodule
  """

  confirmPrompt = cli.Flag(names=['-y', '--yes'], default=False,
    help='Answer warning prompts with yes automatically')
  toRemote = cli.Flag(names=['-r', '--remote'], default=False,
    help='Resets to the remote branch, deleting any unpushed commits')

  def main(self):
    print('Resetting all submodules')
    if self.toRemote:
      if not self.confirmPrompt:
        print('WARNING: This will DELETE UNCOMMITED CHANGES and DELETE UNPUSHED COMMITS, do you want to continue?')
        if not YesNoTrice():
          return 1
    else:
      if not self.confirmPrompt:
        print('WARNING: This will DELETE UNCOMMITED CHANGES, do you want to continue?')
        if not YesNoTwice():
          return 1
    ResetAll(self.parent.repo, self.toRemote)
    return 0


@MetaborgReleng.subcommand("set-versions")
class MetaborgRelengSetVersions(cli.Application):
  """
  Sets Maven and Eclipse version numbers to given version number
  """

  fromVersion = cli.SwitchAttr(names=['-f', '--from'], argtype=str, mandatory=True,
    help='Maven version to change from')
  toVersion = cli.SwitchAttr(names=['-t', '--to'], argtype=str, mandatory=True,
    help='Maven version to change from')

  commit = cli.Flag(names=['-c', '--commit'], default=False,
    help='Commit changed files')
  dryRun = cli.Flag(names=['-d', '--dryrun'], default=False,
    help='Do not modify or commit files, just print operations')
  confirmPrompt = cli.Flag(names=['-y', '--yes'], default=False,
    help='Answer warning prompts with yes automatically')

  def main(self):
    if self.confirmPrompt and not self.dryRun:
      if self.commit:
        print(
          'WARNING: This will CHANGE and COMMIT pom.xml, MANIFEST.MF, and feature.xml files, do you want to continue?')
      else:
        print('WARNING: This will CHANGE pom.xml, MANIFEST.MF, and feature.xml files, do you want to continue?')
        if not YesNo():
          return 1
    SetVersions(self.parent.repo, self.fromVersion, self.toVersion, True, self.dryRun, self.commit)
    return 0


@MetaborgReleng.subcommand("build")
class MetaborgRelengBuild(cli.Application):
  """
  Builds one or more components of spoofax-releng
  """

  buildStratego = cli.Flag(
    names=['-s', '--build-stratego'], default=False,
    help='Build StrategoXT instead of downloading it',
    group='StrategoXT switches'
  )
  bootstrapStratego = cli.Flag(
    names=['-b', '--bootstrap-stratego'], default=False,
    help='Bootstrap StrategoXT instead of building it',
    group='StrategoXT switches'
  )
  noStrategoTest = cli.Flag(
    names=['-t', '--no-stratego-test'], default=False,
    help='Skip StrategoXT tests',
    group='StrategoXT switches'
  )

  qualifier = cli.SwitchAttr(
    names=['-q', '--qualifier'], argtype=str, default=None,
    excludes=['--now-qualifier'],
    help='Qualifier to use',
    group='Build switches'
  )
  nowQualifier = cli.Flag(
    names=['-n', '--now-qualifier'], default=None,
    excludes=['--qualifier'],
    help='Use current time as qualifier instead of latest commit date',
    group='Build switches'
  )

  cleanRepo = cli.Flag(
    names=['-c', '--clean-repo'], default=False,
    help='Clean MetaBorg artifacts from the local repository before building',
    group='Build switches'
  )
  noDeps = cli.Flag(
    names=['-e', '--no-deps'], default=False,
    excludes=['--clean-repo'],
    help='Do not build dependencies, just build given components',
    group='Build switches'
  )
  deployKindStr = cli.SwitchAttr(
    names=['-d', '--deploy'], argtype=str, default=None,
    help='Deploy artifacts to an artifact server. Choose from: {}'.format(', '.join(DeployKind.keys())),
    group='Build switches'
  )
  copyArtifacts = cli.SwitchAttr(
    names=['-a', '--copy-artifacts'], argtype=str, default=None,
    help='Copy produced artifacts to given location',
    group='Build switches'
  )
  generateJavaDoc = cli.Flag(
    names=['-j', '--generate-javadoc'], default=False,
    help="Generate and attach JavaDoc for Java projects",
    group='Build switches'
  )

  stack = cli.SwitchAttr(
    names=['--stack'], default="16M",
    help="JVM stack size",
    group='JVM switches'
  )
  minHeap = cli.SwitchAttr(
    names=['--min-heap'], default="2G",
    help="JVM minimum heap size",
    group='JVM switches'
  )
  maxHeap = cli.SwitchAttr(
    names=['--max-heap'], default="2G",
    help="JVM maximum heap size",
    group='JVM switches'
  )

  noClean = cli.Flag(
    names=['-u', '--no-clean'], default=False,
    help='Do not run the clean phase in Maven builds',
    group='Maven switches'
  )
  skipTests = cli.Flag(
    names=['-y', '--skip-tests'], default=False,
    help="Skip tests",
    group='Maven switches'
  )
  settings = cli.SwitchAttr(
    names=['-i', '--settings'], argtype=str, default=None,
    help='Maven settings file location',
    group='Maven switches'
  )
  globalSettings = cli.SwitchAttr(
    names=['-g', '--global-settings'], argtype=str, default=None,
    help='Global Maven settings file location',
    group='Maven switches')
  localRepo = cli.SwitchAttr(
    names=['-l', '--local-repository'], argtype=str, default=None,
    help='Local Maven repository location',
    group='Maven switches'
  )
  offline = cli.Flag(
    names=['-O', '--offline'], default=False,
    help="Pass --offline flag to Maven",
    group='Maven switches'
  )
  debug = cli.Flag(
    names=['-D', '--debug'], default=False,
    excludes=['--quiet'],
    help="Pass --debug and --errors flag to Maven",
    group='Maven switches'
  )
  quiet = cli.Flag(
    names=['-Q', '--quiet'], default=False,
    excludes=['--debug'],
    help="Pass --quiet flag to Maven",
    group='Maven switches'
  )

  noNative = cli.Flag(
    names=['-N', '--no-native'], default=False,
    help="Gradle won't use native services",
    group='Gradle switches'
  )
  noDaemon = cli.Flag(
    names=['--no-daemon'], default=False,
    help="Gradle won't use its build daemon",
    group='Gradle switches'
  )

  bintrayUsername = cli.SwitchAttr(
    names=['--bintray-username'], argtype=str, default=None,
    help='Bintray username to use for deploying. When not set, defaults to the BINTRAY_USERNAME environment variable. '
         'When the environment variable is also not set, deploying to bintray is disabled',
    group='Bintray switches'
  )
  bintrayKey = cli.SwitchAttr(
    names=['--bintray-key'], argtype=str, default=None,
    help='Bintray key to use for deploying. When not set, defaults to the BINTRAY_KEY environment variable. '
         'When the environment variable is also not set, deploying to bintray is disabled',
    group='Bintray switches'
  )
  bintrayVersion = cli.SwitchAttr(
    names=['--bintray-version'], argtype=str, default=None,
    help='Version to use for deploying to Bintray. When not set, deploying to bintray is disabled',
    group='Bintray switches'
  )

  def main(self, *components):
    repo = self.parent.repo
    builder = RelengBuilder(repo, buildDeps=not self.noDeps)

    if len(components) == 0:
      print('No components specified, pass one or more of the following components to build:')
      print(', '.join(builder.targets))
      return 1

    builder.copyArtifactsTo = self.copyArtifacts

    builder.clean = not self.noClean
    if self.deployKindStr:
      if not DeployKind.exists(self.deployKindStr):
        print('ERROR: deploy kind {} does not exist'.format(self.deployKindStr))
        return 1
      builder.deployKind = DeployKind[self.deployKindStr].value

    builder.skipTests = self.skipTests

    builder.offline = self.offline

    builder.debug = self.debug
    builder.quiet = self.quiet

    if self.qualifier:
      qualifier = self.qualifier
    elif self.nowQualifier:
      qualifier = create_now_qualifier(repo)
    else:
      qualifier = None
    builder.qualifier = qualifier

    builder.generateJavaDoc = self.generateJavaDoc

    builder.buildStratego = self.buildStratego
    builder.bootstrapStratego = self.bootstrapStratego
    builder.testStratego = not self.noStrategoTest

    builder.mavenSettingsFile = self.settings
    builder.mavenGlobalSettingsFile = self.globalSettings
    builder.mavenCleanLocalRepo = self.cleanRepo
    builder.mavenLocalRepo = self.localRepo
    builder.mavenOpts = '-Xss{} -Xms{} -Xmx{}'.format(self.stack, self.minHeap, self.maxHeap)

    builder.gradleNoNative = self.noNative
    builder.gradleDaemon = False if self.noDaemon else None

    builder.bintrayUsername = self.bintrayUsername or os.environ.get('BINTRAY_USERNAME')
    builder.bintrayKey = self.bintrayKey or os.environ.get('BINTRAY_KEY')
    builder.bintrayVersion = self.bintrayVersion

    try:
      builder.build(*components)
      return 0
    except RuntimeError as detail:
      print(str(detail))
      return 1


@MetaborgReleng.subcommand("release")
class MetaborgRelengRelease(cli.Application):
  """
  Performs an interactive release to deploy a new release version
  """

  nextDevelopVersion = cli.SwitchAttr(
    names=['-e', '--next-develop-version'], argtype=str, default=None,
    help='Maven version to set on the development branch after releasing. If not set, the development branch is left untouched',
  )

  deployKindStr = cli.SwitchAttr(
    names=['-d', '--deploy-kind'], argtype=str, mandatory=True,
    help='Kind of release, to determine where to deploy artifacts. Choose from: {}'.format(
      ', '.join(DeployKind.keys())),
  )

  bootstrapStratego = cli.Flag(
    names=['-b', '--bootstrap-stratego'], default=False,
    help='Bootstrap StrategoXT instead of building it',
    group='StrategoXT switches'
  )
  noStrategoTest = cli.Flag(
    names=['-t', '--no-stratego-test'], default=False,
    help='Skip StrategoXT tests',
    group='StrategoXT switches'
  )

  bintrayUsername = cli.SwitchAttr(
    names=['--bintray-username'], argtype=str, default=None,
    help='Bintray username to use for deploying. When not set, defaults to the BINTRAY_USERNAME environment variable. '
         'When the environment variable is also not set, deploying to bintray is disabled',
    group='Bintray switches'
  )
  bintrayKey = cli.SwitchAttr(
    names=['--bintray-key'], argtype=str, default=None,
    help='Bintray key to use for deploying. When not set, defaults to the BINTRAY_KEY environment variable. '
         'When the environment variable is also not set, deploying to bintray is disabled',
    group='Bintray switches'
  )

  def main(self, releaseBranch, nextReleaseVersion, developBranch, curDevelopVersion):
    """
    Performs an interactive release to deploy a new release version

    :param releaseBranch: Git branch to release to
    :param nextReleaseVersion: Next Maven version for the release branch

    :param developBranch: Git development branch to release from
    :param curDevelopVersion: Current Maven version for the development branch
    :return:
    """

    repo = self.parent.repo
    repoDir = repo.working_tree_dir
    scriptDir = path.dirname(path.realpath(__file__))
    if CommonPrefix([repoDir, scriptDir]) == repoDir:
      print(
        'Cannot perform release on the same repository this script is contained in, please set another repository '
        'using the -r/--repo switch.')
      return 1

    if not DeployKind.exists(self.deployKindStr):
      print('ERROR: deploy kind {} does not exist'.format(self.deployKindStr))
      return 1
    deployKind = DeployKind[self.deployKindStr].value
    if not deployKind.bintrayRepoName:
      print('ERROR: no Bintray repository was set, cannot deploy. Choose a different deploy kind')
      return 1
    if deployKind.mavenIsSnapshot:
      print('ERROR: cannot release snapshots. Choose a different deploy kind')
      return 1

    release = MetaborgRelease(repo, releaseBranch, nextReleaseVersion, developBranch, curDevelopVersion, deployKind)

    release.nextDevelopVersion = self.nextDevelopVersion

    release.bootstrapStratego = self.bootstrapStratego
    release.testStratego = not self.noStrategoTest

    release.bintrayUsername = self.bintrayUsername or os.environ.get('BINTRAY_USERNAME')
    release.bintrayKey = self.bintrayKey or os.environ.get('BINTRAY_KEY')

    if not (release.bintrayUsername and release.bintrayKey):
      print('ERROR: no Bintray username and/or key was set, cannot deploy')
      return 1

    print('Performing release')
    release.release()

    return 0


@MetaborgReleng.subcommand("bootstrap")
class MetaborgRelengBootstrap(cli.Application):
  """
  Performs an interactive bootstrap to deploy a new baseline
  """

  curVersion = cli.SwitchAttr(names=['--cur-ver'], argtype=str, mandatory=True,
    help="Current Maven version")
  curBaselineVersion = cli.SwitchAttr(names=['--cur-base-ver'], argtype=str, mandatory=True,
    help="Current Maven baseline version")

  def main(self):
    print('Performing interactive bootstrap')

    repo = self.parent.repo

    Bootstrap(repo, self.curVersion, self.curBaselineVersion)
    return 0


@MetaborgReleng.subcommand("gen-eclipse")
class MetaborgRelengGenEclipse(cli.Application):
  """
  Generate a plain Eclipse instance
  """

  destination = cli.SwitchAttr(
    names=['-d', '--destination'], argtype=str, mandatory=True,
    help='Path to generate the Eclipse instance at'
  )

  moreRepos = cli.SwitchAttr(
    names=['-r', '--repo'], argtype=str, list=True,
    help='Additional repositories to install units from'
  )
  moreIUs = cli.SwitchAttr(
    names=['-i', '--install'], argtype=str, list=True,
    help='Additional units to install'
  )

  os = cli.SwitchAttr(
    names=['-o', '--os'], argtype=str, default=None,
    help='OS to generate Eclipse for. Defaults to OS of this computer. '
         'Choose from: macosx, linux, win32'
  )
  arch = cli.SwitchAttr(
    names=['-h', '--arch'], argtype=str, default=None,
    help='Processor architecture to generate Eclipse for. Defaults to architecture of this computer. '
         'Choose from: x86, x86_64'
  )

  archive = cli.Flag(
    names=['-a', '--archive'], default=False,
    help='Archive the Eclipse instance at destination instead. '
         'Results in a tar.gz file on UNIX systems, zip file on Windows systems'
  )
  addJre = cli.Flag(
    names=['-j', '--add-jre'], default=False,
    help='Embeds a Java runtime in the Eclipse instance.'
  )
  archiveJreSeparately = cli.Flag(
    names=['--archive-jre-separately'], default=False,
    requires=['--archive', '--add-jre'],
    help='Archive the non-JRE and JRE embedded versions separately, resulting in 2 archives'
  )

  def main(self):
    print('Generating plain Eclipse instance')

    if self.os:
      if not Os.exists(self.os):
        print('ERROR: operating system {} does not exist'.format(self.os))
        return 1
      eclipseOs = Os[self.os].value
    else:
      eclipseOs = Os.get_current()

    if self.arch:
      if not Arch.exists(self.arch):
        print('ERROR: architecture {} does not exist'.format(self.arch))
        return 1
      eclipseArch = Arch[self.arch].value
    else:
      eclipseArch = Arch.get_current()

    generator = MetaborgEclipseGenerator(self.parent.repo.working_tree_dir, self.destination,
      spoofax=False, moreRepos=self.moreRepos, moreIUs=self.moreIUs)
    generator.generate(os=eclipseOs, arch=eclipseArch, fixIni=True, addJre=self.addJre,
      archiveJreSeparately=self.archiveJreSeparately, archive=self.archive)

    return 0


@MetaborgReleng.subcommand("gen-spoofax")
class MetaborgRelengGenSpoofax(cli.Application):
  """
  Generate an Eclipse instance for Spoofax users
  """

  destination = cli.SwitchAttr(
    names=['-d', '--destination'], argtype=str, mandatory=True,
    help='Path to generate the Eclipse instance at'
  )

  spoofaxRepo = cli.SwitchAttr(
    names=['--spoofax-repo'], argtype=str, mandatory=False,
    excludes=['--local-spoofax-repo'],
    help='Spoofax repository used to install Spoofax plugins'
  )
  localSpoofax = cli.Flag(
    names=['-l', '--local-spoofax-repo'], default=False,
    excludes=['--spoofax-repo'],
    help='Use locally built Spoofax updatesite'
  )
  noMeta = cli.Flag(names=['-m', '--nometa'], default=False,
    help="Don't install Spoofax meta-plugins such as the Stratego compiler and editor. "
         'Results in a smaller Eclipse instance, but it can only be used to run Spoofax languages, not develop them'
  )

  moreRepos = cli.SwitchAttr(
    names=['-r', '--repo'], argtype=str, list=True,
    help='Additional repositories to install units from'
  )
  moreIUs = cli.SwitchAttr(
    names=['-i', '--install'], argtype=str, list=True,
    help='Additional units to install'
  )

  os = cli.SwitchAttr(
    names=['-o', '--os'], argtype=str, default=None,
    help='OS to generate Eclipse for. Defaults to OS of this computer. '
         'Choose from: macosx, linux, win32'
  )
  arch = cli.SwitchAttr(
    names=['-h', '--arch'], argtype=str, default=None,
    help='Processor architecture to generate Eclipse for. Defaults to architecture of this computer. '
         'Choose from: x86, x86_64'
  )

  archive = cli.Flag(
    names=['-a', '--archive'], default=False,
    help='Archive the Eclipse instance at destination instead. '
         'Results in a tar.gz file on UNIX systems, zip file on Windows systems'
  )
  addJre = cli.Flag(
    names=['-j', '--add-jre'], default=False,
    help='Embeds a Java runtime in the Eclipse instance.'
  )
  archiveJreSeparately = cli.Flag(
    names=['--archive-jre-separately'], default=False,
    requires=['--archive', '--add-jre'],
    help='Archive the non-JRE and JRE embedded versions separately, resulting in 2 archives'
  )

  def main(self):
    print('Generating Eclipse instance for Spoofax users')

    if self.os:
      if not Os.exists(self.os):
        print('ERROR: operating system {} does not exist'.format(self.os))
        return 1
      eclipseOs = Os[self.os].value
    else:
      eclipseOs = Os.get_current()

    if self.arch:
      if not Arch.exists(self.arch):
        print('ERROR: architecture {} does not exist'.format(self.arch))
        return 1
      eclipseArch = Arch[self.arch].value
    else:
      eclipseArch = Arch.get_current()

    generator = MetaborgEclipseGenerator(self.parent.repo.working_tree_dir, self.destination,
      spoofax=True, spoofaxRepo=self.spoofaxRepo,
      spoofaxRepoLocal=self.localSpoofax, langDev=not self.noMeta, lwbDev=not self.noMeta, moreRepos=self.moreRepos,
      moreIUs=self.moreIUs)
    generator.generate(os=eclipseOs, arch=eclipseArch, fixIni=True, addJre=self.addJre,
      archiveJreSeparately=self.archiveJreSeparately, archive=self.archive, archivePrefix='spoofax')

    return 0


@MetaborgReleng.subcommand("gen-mvn-settings")
class MetaborgRelengGenMvnSettings(cli.Application):
  """
  Generate a Maven settings file with MetaBorg repositories and a Spoofax update site
  """

  destination = cli.SwitchAttr(names=['-d', '--destination'], argtype=str, mandatory=False,
    default=MetaborgMavenSettingsGeneratorGenerator.defaultSettingsLocation,
    help='Path to generate Maven settings file at')
  metaborgReleases = cli.SwitchAttr(names=['-r', '--metaborg-releases'], argtype=str, mandatory=False,
    default=MetaborgMavenSettingsGeneratorGenerator.defaultReleases, help='Maven repository for MetaBorg releases')
  metaborgSnapshots = cli.SwitchAttr(names=['-s', '--metaborg-snapshots'], argtype=str, mandatory=False,
    default=MetaborgMavenSettingsGeneratorGenerator.defaultSnapshots, help='Maven repository for MetaBorg snapshots')
  noMetaborgSnapshots = cli.Flag(names=['-S', '--no-metaborg-snapshots'], default=False,
    help="Don't add a Maven repository for MetaBorg snapshots")
  spoofaxUpdateSite = cli.SwitchAttr(names=['-u', '--spoofax-update-site'], argtype=str, mandatory=False,
    default=MetaborgMavenSettingsGeneratorGenerator.defaultUpdateSite, help='Eclipse update site for Spoofax plugins')
  noSpoofaxUpdateSite = cli.Flag(names=['-U', '--no-spoofax-update-site'], default=False,
    help="Don't add an Eclipse update site for Spoofax plugins")
  centralMirror = cli.SwitchAttr(names=['-m', '--central-mirror'], argtype=str, mandatory=False,
    default=MetaborgMavenSettingsGeneratorGenerator.defaultMirror, help='Maven repository for mirroring Maven central')
  confirmPrompt = cli.Flag(names=['-y', '--yes'], default=False,
    help='Answer warning prompts with yes automatically')

  def main(self):
    print('Generating Maven settings file')

    if not self.confirmPrompt and path.isfile(self.destination):
      print('Maven settings file already exists at {}, would you like to overwrite it?'.format(self.destination))
      if not YesNo():
        return 1

    if self.noMetaborgSnapshots:
      metaborgSnapshots = None
    else:
      metaborgSnapshots = self.metaborgSnapshots

    if self.noSpoofaxUpdateSite:
      spoofaxUpdateSite = None
    else:
      spoofaxUpdateSite = self.spoofaxUpdateSite

    generator = MetaborgMavenSettingsGeneratorGenerator(location=self.destination,
      metaborgReleases=self.metaborgReleases,
      metaborgSnapshots=metaborgSnapshots, spoofaxUpdateSite=spoofaxUpdateSite,
      centralMirror=self.centralMirror)
    generator.generate()

    return 0


@MetaborgReleng.subcommand("gen-icons")
class MetaborgRelengGenIcons(cli.Application):
  """
  Generates the PNG, ICO and ICNS versions of the Spoofax icons
  """

  destination = cli.SwitchAttr(names=['-d', '--destination'], argtype=str, mandatory=True,
    help='Path to generate the icons at')
  text = cli.SwitchAttr(names=['-t', '--text'], argtype=str, mandatory=False,
    default='', help='Text to show on the icons')

  def main(self):
    repo = self.parent.repo
    GenerateIcons(repo, self.destination, self.text)
    print('Done!')


@MetaborgReleng.subcommand("qualifier")
class MetaborgRelengQualifier(cli.Application):
  """
  Prints the current qualifier based on the current branch and latest commit date in all submodules.
  """

  def main(self):
    print(create_qualifier(self.parent.repo))


@MetaborgReleng.subcommand("changed")
class MetaborgRelengChanged(cli.Application):
  """
  Returns 0 and prints the qualifer if repository has changed since last invocation of this command, based on the
  current branch and latest commit date in all submodules. Returns 1 otherwise.
  """

  destination = cli.SwitchAttr(names=['-d', '--destination'], argtype=str, mandatory=False,
    default='.qualifier', help='Path to read/write the last qualifier to')

  forceChange = cli.Flag(names=['-f', '--force-change'], default=False, help='Force a change, always return 0')

  def main(self):
    changed, qualifier = repo_changed(self.parent.repo, self.destination)
    if self.forceChange or changed:
      print(qualifier)
      return 0
    return 1

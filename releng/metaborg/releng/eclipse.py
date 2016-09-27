from eclipsegen.generate import EclipseGenerator


class MetaborgEclipseGenerator(EclipseGenerator):
  # Eclipse
  eclipseRepos = [
    # Eclipse Neon (4.6)
    'http://eclipse.mirror.triple-it.nl/releases/neon/',
    'http://eclipse.mirror.triple-it.nl/eclipse/updates/4.6',
    # Gradle buildship 2.0 milestones
    'http://download.eclipse.org/buildship/updates/e45/milestones/2.x/',
  ]
  eclipseIUs = [
    # Platform
    'org.eclipse.platform.ide',
    'org.eclipse.platform.feature.group',
    # Common
    'org.eclipse.epp.package.common.feature.feature.group',
    # P2 update UI
    'org.eclipse.equinox.p2.user.ui.feature.group',
    # Marketplace
    'org.eclipse.epp.mpc.feature.group',
    # Package
    'epp.package.java',
    # Java development
    'org.eclipse.jdt.feature.group',
    # Maven
    'org.eclipse.m2e.feature.feature.group',
    # Gradle
    'org.eclipse.buildship.feature.group',
    # XML editors
    'org.eclipse.wst.xml_ui.feature.feature.group',
    # Code recommenders
    'org.eclipse.recommenders.rcp.feature.feature.group',
    # Git
    'org.eclipse.egit.feature.group',
    'org.eclipse.jgit.feature.group'
  ]
  eclipseLangDevIUs = [
    # Eclipse plugin development
    'org.eclipse.pde.feature.group'
  ]
  eclipseLwbDevIUs = [
    # Eclipse platform sources
    'org.eclipse.platform.source.feature.group',
    # Eclipse plugin development sources
    'org.eclipse.pde.source.feature.group',
    # Java development plugin sources
    'org.eclipse.jdt.source.feature.group'
  ]

  # M2E plugins
  m2ePluginRepos = [
    'http://download.jboss.org/jbosstools/updates/m2e-extensions/m2e-jdt-compiler/',
    'http://download.jboss.org/jbosstools/updates/m2e-extensions/m2e-apt',
    'http://repo1.maven.org/maven2/.m2e/connectors/m2eclipse-buildhelper/0.15.0/N/0.15.0.201405280027/',
    'http://repo1.maven.org/maven2/.m2e/connectors/m2eclipse-tycho/0.7.0/N/LATEST/'
  ]
  m2ePluginIUs = [
    # Eclipse JDT compiler support
    'org.jboss.tools.m2e.jdt.feature.feature.group',
    # Java annotation processing support
    'org.jboss.tools.maven.apt.feature.feature.group',
    # Build helper plugin support
    'org.sonatype.m2e.buildhelper.feature.feature.group'
  ]
  m2ePluginLangDevIUs = [
    # Tycho support
    'org.sonatype.tycho.m2e.feature.feature.group'
  ]
  m2ePluginLwbDevIUs = [
  ]

  spoofaxRepo = 'http://download.spoofax.org/update/nightly/'
  spoofaxRepoLocal = 'spoofax-eclipse/org.metaborg.spoofax.eclipse.updatesite/target/repository'
  spoofaxIUs = ['org.metaborg.spoofax.eclipse.feature.feature.group']
  spoofaxLangDevIUs = [
    'org.metaborg.spoofax.eclipse.meta.feature.feature.group',
    'org.metaborg.spoofax.eclipse.meta.m2e.feature.feature.group'
  ]

  def __init__(self, workingDir, destination, config, spoofax=True, spoofaxRepo=None, spoofaxRepoLocal=False,
      langDev=True, lwbDev=True, moreRepos=None, moreIUs=None, archive=False):
    if spoofaxRepoLocal:
      spoofaxRepo = MetaborgEclipseGenerator.spoofaxRepoLocal
    elif not spoofaxRepo:
      spoofaxRepo = MetaborgEclipseGenerator.spoofaxRepo

    if lwbDev:
      langDev = True

    if not moreRepos:
      moreRepos = []
    if not moreIUs:
      moreIUs = []

    repos = []
    ius = []

    # Eclipse
    repos.extend(MetaborgEclipseGenerator.eclipseRepos)
    ius.extend(MetaborgEclipseGenerator.eclipseIUs)
    if langDev:
      ius.extend(MetaborgEclipseGenerator.eclipseLangDevIUs)
    if lwbDev:
      ius.extend(MetaborgEclipseGenerator.eclipseLwbDevIUs)

    # M2E plugins
    repos.extend(MetaborgEclipseGenerator.m2ePluginRepos)
    ius.extend(MetaborgEclipseGenerator.m2ePluginIUs)
    if langDev:
      ius.extend(MetaborgEclipseGenerator.m2ePluginLangDevIUs)
    if lwbDev:
      ius.extend(MetaborgEclipseGenerator.m2ePluginLwbDevIUs)

    # Spoofax
    if spoofax:
      repos.append(spoofaxRepo)
      ius.extend(MetaborgEclipseGenerator.spoofaxIUs)
      if langDev:
        ius.extend(MetaborgEclipseGenerator.spoofaxLangDevIUs)

    repos.extend(moreRepos)
    ius.extend(moreIUs)

    EclipseGenerator.__init__(self, workingDir, destination, config, repos, ius, archive)

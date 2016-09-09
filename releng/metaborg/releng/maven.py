from mavenpy.settings import MavenSettingsGenerator


class MetaborgMavenSettingsGeneratorGenerator(MavenSettingsGenerator):
  defaultSettingsLocation = MavenSettingsGenerator.user_settings_location()
  defaultReleases = 'http://artifacts.metaborg.org/content/repositories/releases/'
  defaultSnapshots = 'http://artifacts.metaborg.org/content/repositories/in4303/'
  defaultUpdateSite = 'http://download.spoofax.org/update/nightly/'
  defaultMirror = 'http://artifacts.metaborg.org/content/repositories/central/'

  def __init__(self, location=defaultSettingsLocation, metaborgReleases=defaultReleases,
      metaborgSnapshots=defaultSnapshots, spoofaxUpdateSite=defaultUpdateSite,
      centralMirror=defaultMirror):
    repositories = []
    if metaborgReleases:
      repositories.append(
        ('add-metaborg-release-repos', 'metaborg-release-repo', metaborgReleases, None, True, False, True))
    if metaborgSnapshots:
      repositories.append(
        ('add-metaborg-snapshot-repos', 'metaborg-snapshot-repo', metaborgSnapshots, None, False, True, True))
    if spoofaxUpdateSite:
      repositories.append(
        ('add-spoofax-eclipse-repos', 'spoofax-eclipse-repo', spoofaxUpdateSite, 'p2', False, False, False))

    mirrors = []
    if centralMirror:
      mirrors.append(('metaborg-central-mirror', centralMirror, 'central'))

    MavenSettingsGenerator.__init__(self, location=location, repositories=repositories, mirrors=mirrors)

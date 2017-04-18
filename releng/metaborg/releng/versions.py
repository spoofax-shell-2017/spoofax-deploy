import os
import re
import xml.etree.ElementTree as ET
from os import path

from metaborg.util.path import CommonPrefix


def ToEclipseVersion(mavenVersion):
  match = re.compile(r'(\d+)\.(\d+)\.(\d+)-(.+)').match(mavenVersion)
  if match is not None:
    version = '{}.{}.{}.{}'.format(match.group(1), match.group(2), match.group(3), match.group(4))
  else:
    version = mavenVersion.replace('-', '.')
  return version.replace('SNAPSHOT', 'qualifier')


def SetVersions(repo, oldMavenVersion, newMavenVersion, dryRun=False, commit=False):
  baseDir = repo.working_tree_dir
  ignoreDirs = ['eclipse-installations', 'target', '_attic', 'metaborg-sl']

  oldEclipseVersion = ToEclipseVersion(oldMavenVersion)
  newEclipseVersion = ToEclipseVersion(newMavenVersion)
  if oldEclipseVersion == oldMavenVersion:
    oldVersionString = oldMavenVersion
  else:
    oldVersionString = '{} / {}'.format(oldMavenVersion, oldEclipseVersion)
  if newEclipseVersion == newMavenVersion:
    newVersionString = newMavenVersion
  else:
    newVersionString = '{} / {}'.format(newMavenVersion, newEclipseVersion)

  changedFiles = []

  print('Old version {}'.format(oldVersionString))
  print('New version {}'.format(newVersionString))

  def FindFiles(root, pattern):
    allFiles = []
    for rootDir, dirs, files in os.walk(root):
      for ignoreDir in ignoreDirs:
        if ignoreDir in dirs:
          dirs.remove(ignoreDir)
      for file in files:
        if file.endswith(pattern):
          allFiles.append(os.path.join(rootDir, file))
    return allFiles

  def ReplaceInFile(replaceFile, pattern, replacement):
    with open(replaceFile) as fileHandle:
      text = fileHandle.read()
    if pattern in text:
      print('Setting version in {}'.format(replaceFile))
      text = text.replace(pattern, replacement)
      changedFiles.append(replaceFile)
      if dryRun:
        return
      with open(replaceFile, "w") as fileHandle:
        fileHandle.write(text)

  def IsMavenPomFile(pomFile):
    try:
      xmlRoot = ET.parse(pomFile)
    except ET.ParseError:
      return False
    project = xmlRoot.getroot()
    if project is None or project.tag != '{http://maven.apache.org/POM/4.0.0}project':
      return False
    return True

  def IsGeneratedManifestFile(manifestFile):
    with open(manifestFile) as fileHandle:
      text = fileHandle.read()
    return 'Bnd-LastModified' in text


  # Java property file versions
  print('Setting versions in Java property files; {} -> {}'.format(oldMavenVersion, newMavenVersion))
  for file in FindFiles(baseDir, '.properties'):
    ReplaceInFile(file, oldMavenVersion, newMavenVersion)

  # Maven versions
  print('Setting versions in Maven POM files; {} -> {}'.format(oldMavenVersion, newMavenVersion))
  for file in FindFiles(baseDir, 'pom.xml'):
    if IsMavenPomFile(file):
      ReplaceInFile(file, oldMavenVersion, newMavenVersion)

  print('Setting versions in Maven extension files; {} -> {}'.format(oldMavenVersion, newMavenVersion))
  for file in FindFiles(baseDir, 'extensions.xml'):
    ReplaceInFile(file, oldMavenVersion, newMavenVersion)

  # Gradle versions
  print('Setting versions in Gradle build files; {} -> {}'.format(oldMavenVersion, newMavenVersion))
  for file in FindFiles(baseDir, 'build.gradle'):
    ReplaceInFile(file, oldMavenVersion, newMavenVersion)

  print('Setting versions in Gradle settings files; {} -> {}'.format(oldMavenVersion, newMavenVersion))
  for file in FindFiles(baseDir, 'settings.gradle'):
    ReplaceInFile(file, oldMavenVersion, newMavenVersion)

  # Spoofax Core versions
  '''
  Special handling of org.metaborg.core.MetaborgConstants Java class. Need to set the METABORG_VERSION constant to the
  Maven version.
  '''
  print('Setting version in MetaborgConstants Java class; {} -> {}'.format(oldMavenVersion, newMavenVersion))
  ReplaceInFile(os.path.join(baseDir, 'spoofax', 'org.metaborg.core', 'src', 'main', 'java', 'org', 'metaborg', 'core',
    'MetaborgConstants.java'), oldMavenVersion, newMavenVersion)

  print('Setting versions in metaborg.yaml files; {} -> {}'.format(oldMavenVersion, newMavenVersion))
  for file in FindFiles(baseDir, 'metaborg.yaml'):
    ReplaceInFile(file, oldMavenVersion, newMavenVersion)

  # Eclipse version
  '''
  Special handling for org.metaborg.spoofax.eclipse.updatesite project. Need to set the version in the pom file to the
  Eclipse version instead of the Maven version, otherwise Tycho will fail the build.
  '''
  print('Setting version in org.metaborg.spoofax.eclipse.updatesite POM file; {} -> {}'.format(oldEclipseVersion,
    newEclipseVersion))
  ReplaceInFile(os.path.join(baseDir, 'spoofax-eclipse', 'org.metaborg.spoofax.eclipse.updatesite', 'pom.xml'),
    oldEclipseVersion, newEclipseVersion)

  print('Setting versions in MANIFEST.MF files; {} -> {}'.format(oldEclipseVersion, newEclipseVersion))
  for file in FindFiles(baseDir, 'MANIFEST.MF'):
    if not IsGeneratedManifestFile(file):
      ReplaceInFile(file, oldEclipseVersion, newEclipseVersion)

  print('Setting versions in feature.xml files; {} -> {}'.format(oldEclipseVersion, newEclipseVersion))
  for file in FindFiles(baseDir, 'feature.xml'):
    ReplaceInFile(file, oldEclipseVersion, newEclipseVersion)

  print('Setting versions in site.xml files; {} -> {}'.format(oldEclipseVersion, newEclipseVersion))
  for file in FindFiles(baseDir, 'site.xml'):
    ReplaceInFile(file, oldEclipseVersion, newEclipseVersion)

  # IntelliJ versions
  print('Setting versions in IntelliJ plugin.xml files; {} -> {}'.format(oldMavenVersion, newMavenVersion))
  for file in FindFiles(
      os.path.join(baseDir, 'spoofax-intellij', 'org.metaborg.intellij', 'src', 'main', 'resources', 'META-INF'),
      'plugin.xml'):
    ReplaceInFile(file, oldMavenVersion, newMavenVersion)

  print('Setting versions in IntelliJ text files; {} -> {}'.format(oldMavenVersion, newMavenVersion))
  for file in FindFiles(
      os.path.join(baseDir, 'spoofax-intellij', 'org.metaborg.spoofax-common', 'src', 'main', 'resources'), '.txt'):
    ReplaceInFile(file, oldMavenVersion, newMavenVersion)

  print('Setting versions in IntelliJ updatePlugins.xml files; {} -> {}'.format(oldMavenVersion, newMavenVersion))
  for file in FindFiles(os.path.join(baseDir, 'spoofax-intellij', 'repository'), 'updatePlugins.xml'):
    ReplaceInFile(file, oldMavenVersion, newMavenVersion)

  # Commit changed files
  if commit:
    print('Committing changed files')
    for submodule in repo.submodules:
      print('Submodule {}'.format(submodule.name))
      subrepo = submodule.module()
      subrepoPath = subrepo.working_dir
      filesToAdd = [path.relpath(f, subrepoPath) for f in changedFiles if CommonPrefix([subrepoPath, f]) == subrepoPath]
      if len(filesToAdd) != 0:
        if dryRun:
          print('Changed files {}'.format(filesToAdd))
        else:
          print('Adding files {} and committing'.format(filesToAdd))
          if len(subrepo.index.add(filesToAdd)) != 0:
            subrepo.index.commit('Set version to {}'.format(newVersionString))

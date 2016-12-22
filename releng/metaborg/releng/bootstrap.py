import os
import shelve
from datetime import datetime
from os import path

from metaborg.releng.build import RelengBuilder
from metaborg.releng.versions import SetVersions
from metaborg.util.git import PushAll
from metaborg.util.prompt import YesNo


def Bootstrap(repo, curVersion, curBaselineVersion):
  with shelve.open(_ShelveLocation()) as db:
    if 'state' in db:
      state = db['state']
    else:
      state = 0

    if 'version' in db:
      nextBaselineVersion = db['version']
    else:
      curVersionStripped = curVersion.replace('-SNAPSHOT', '')
      qualifier = datetime.now().strftime('%Y%m%d-%H%M%S')
      nextBaselineVersion = '{}-baseline-{}'.format(curVersionStripped, qualifier)
      db['version'] = nextBaselineVersion

    def Step0():
      dirtyRepos = []
      for submodule in repo.submodules:
        subrepo = submodule.module()
        if subrepo.is_dirty():
          dirtyRepos.append(submodule.name)
      if len(dirtyRepos) > 0:
        print('You have uncommitted changes in submodules {}, are you sure you want to continue?'.format(dirtyRepos))
        if not YesNo():
          return
      print('Step 1: for each submodule: set version from the current version to the next baseline version')
      SetVersions(repo, curVersion, nextBaselineVersion, dryRun=False, commit=False)
      db['state'] = 1
      db['version'] = nextBaselineVersion
      print('Please check if versions have been set correctly, then continue')

    def Step1():
      try:
        builder = RelengBuilder(repo)
        builder.release = True
        builder.buildStratego = True
        builder.testStratego = True
        builder.build('languages', 'spt')
      except Exception as detail:
        print('Test release build failed, not continuing to the next step')
        print(str(detail))
        return
      db['state'] = 2
      print('Please check if the built artifacts work, then continue')

    def Step2():
      print('Step 3: perform release deployment')
      builder = RelengBuilder(repo)
      builder.deploy = True
      builder.release = True
      builder.clean = False
      builder.skipExpensive = True
      builder.skipTests = True
      builder.buildStratego = True
      builder.testStratego = False
      builder.build('languages', 'spt')
      db['state'] = 3
      print('Please check if deploying succeeded, and manually deploy extra artifacts, then continue')

    def Step3():
      print(
        'Step 4: for each submodule: revert to previous version, and update baseline version to the next baseline '
        'version')
      SetVersions(repo, nextBaselineVersion, curVersion, dryRun=False, commit=False)
      SetVersions(repo, curBaselineVersion, nextBaselineVersion, dryRun=False, commit=True)
      print('Updating submodule revisions')
      repo.git.add('--all')
      repo.index.commit('Update submodule revisions')
      db['state'] = 4
      print('Please check if versions have been set correctly, then continue')

    def Step4():
      print('Step 5: push submodules and repository')
      PushAll(repo)
      print('Pushing')
      remote = repo.remote('origin')
      remote.push()
      print('All done!')
      Reset()

    def Reset():
      os.remove(_ShelveLocation())

    steps = {
      0: Step0,
      1: Step1,
      2: Step2,
      3: Step3,
      4: Step4,
    }

    steps[state]()


def _ShelveLocation():
  return path.join(path.expanduser('~'), '.spoofax-releng-bootstrap-state')

import os
import shelve
from os import path

import git

from metaborg.releng.build import RelengBuilder
from metaborg.releng.versions import SetVersions
from metaborg.util.git import CheckoutAll, UpdateAll, TagAll, PushAll
from metaborg.util.prompt import YesNo


def Release(repo, releaseBranchName, developBranchName, curDevelopVersion, nextReleaseVersion, nextDevelopVersion):
  with shelve.open(_ShelveLocation()) as db:
    releaseBranch = repo.heads[releaseBranchName]
    developBranch = repo.heads[developBranchName]

    if 'state' in db:
      state = db['state']
    else:
      state = 0

    def Step0():
      print('Step 0: prepare development branch')
      developBranch.checkout()
      CheckoutAll(repo)
      repo.remotes.origin.pull()
      CheckoutAll(repo)  # Check out again in case .gitmodules was changed.
      UpdateAll(repo)
      submoduleDevBranches = {}
      for submodule in repo.submodules:
        submoduleDevBranches[submodule.name] = submodule.branch
      db['submoduleDevBranches'] = submoduleDevBranches
      db['state'] = 1
      Step1()

    def Step1():
      print('Step 1: prepare release branch')
      releaseBranch.checkout()
      CheckoutAll(repo)
      repo.remotes.origin.pull()
      CheckoutAll(repo)  # Check out again in case .gitmodules was changed.
      UpdateAll(repo)
      submoduleRelBranches = {}
      for submodule in repo.submodules:
        submoduleRelBranches[submodule.name] = submodule.branch
      db['submoduleRelBranches'] = submoduleRelBranches
      db['state'] = 2
      Step2()

    def Step2():
      print('Step 2: merge development branch into release branch')
      try:
        # Merge using 'theirs' to overwrite any changes in the release branch with changes from the development branch
        repo.git.merge('--strategy=recursive', '--strategy-option=theirs', developBranch.name)
      except git.exc.GitCommandError as detail:
        print('Automatic merge failed')
        print(str(detail))
      try:
        # Restore .gitmodules because the submodule branches should not be overwritten by the development branch
        repo.git.checkout('--ours', '--', '.gitmodules')
      except git.exc.GitCommandError as detail:
        print("Restoring '.gitmodules' file failed")
        print(str(detail))
      db['state'] = 3
      print('Please fix any conflicts and commit all changes in the root repository, then continue')

    def Step3():
      if repo.is_dirty():
        print('You have uncommitted changes, are you sure you want to continue?')
        if not YesNo():
          return
      print('Step 3: for each submodule: merge development branch into release branch')
      submoduleDevBranches = db['submoduleDevBranches']
      submoduleRelBranches = db['submoduleRelBranches']
      for submodule in repo.submodules:
        subrepo = submodule.module()
        try:
          print('Merging submodule {}'.format(submodule.name))
          # Use merging strategy 3 from http://stackoverflow.com/a/27338013/499240 to make release branch identical to
          # development branch, while keeping correct parent order.
          submoduleDevBranch = submoduleDevBranches[submodule.name]
          submoduleRelBranch = submoduleRelBranches[submodule.name]
          subrepo.git.merge('--strategy=ours', submoduleDevBranch)
          subrepo.git.checkout('--detach', submoduleDevBranch)
          subrepo.git.reset('--soft', submoduleRelBranch)
          subrepo.git.checkout(submoduleRelBranch)
          subrepo.git.commit('--amend', '-C', 'HEAD')
        except git.exc.GitCommandError as detail:
          print('Automatic merge failed')
          print(str(detail))
      db['state'] = 4
      print('Please fix any conflicts and commit all changes in all submodules, then continue')

    def Step4():
      dirtyRepos = []
      for submodule in repo.submodules:
        subrepo = submodule.module()
        if subrepo.is_dirty():
          dirtyRepos.append(submodule.name)
      if len(dirtyRepos) > 0:
        print('You have uncommitted changes in submodules {}, are you sure you want to continue?'.format(dirtyRepos))
        if not YesNo():
          return
      print('Step 4: for each submodule: set version from the current development version to the next release version')
      SetVersions(repo, curDevelopVersion, nextReleaseVersion, setEclipseVersions=True, dryRun=False, commit=True)
      print('Updating submodule revisions')
      repo.git.add('--all')
      repo.index.commit('Update submodule revisions')
      db['state'] = 5
      print('Please check if versions have been set correctly, then continue')

    def Step5():
      print('Step 5: perform a test release build')
      builder = RelengBuilder(repo)
      builder.copyArtifactsTo = 'dist'
      builder.release = True
      builder.buildStratego = True
      builder.testStratego = True
      try:
        builder.build('all')
      except Exception as detail:
        print('Test release build failed, not continuing to the next step')
        print(str(detail))
        return
      db['state'] = 6
      print('Please check if the built artifact works, then continue')

    def Step6():
      print('Step 6: perform release deployment')
      builder = RelengBuilder(repo)
      builder.copyArtifactsTo = 'dist'
      builder.deploy = True
      builder.release = True
      builder.clean = False
      builder.skipExpensive = True
      builder.skipTests = True
      builder.buildStratego = True
      builder.testStratego = False
      try:
        builder.build('all', 'eclipse-instances')
      except Exception as detail:
        print('Release deployment failed, not continuing to the next step')
        print(str(detail))
        return
      db['state'] = 7
      print('Please check if deploying succeeded, and manually deploy extra artifacts, then continue')

    def Step7():
      print('Step 7: tag release submodules and repository')
      tagName = '{}/{}'.format(releaseBranchName, nextReleaseVersion);
      tagDescription = 'Tag for {} release'.format(nextReleaseVersion)
      TagAll(repo, tagName, tagDescription)
      print('Creating tag {}'.format(tagName))
      repo.create_tag(path=tagName, message=tagDescription)
      db['state'] = 8
      Step8()

    def Step8():
      print('Step 8: push release submodules and repository')
      PushAll(repo)
      PushAll(repo, tags=True)
      print('Pushing')
      remote = repo.remote('origin')
      remote.push()
      remote.push(tags=True)
      db['state'] = 9
      Step9()

    def Step9():
      print('Step 9: switch to development branch')
      developBranch.checkout()
      CheckoutAll(repo)
      db['state'] = 10
      Step10()

    def Step10():
      print(
        'Step 10: for each submodule: set version from the current development version to the next development version')
      SetVersions(repo, curDevelopVersion, nextDevelopVersion, setEclipseVersions=True, dryRun=False, commit=True)
      print('Updating submodule revisions')
      repo.git.add('--all')
      repo.index.commit('Update submodule revisions')
      db['state'] = 11
      print('Please check if versions have been set correctly, then continue')

    def Step11():
      print('Step 11: push development submodules and repository')
      PushAll(repo)
      print('Pushing')
      remote = repo.remote('origin')
      remote.push()
      print('All done!')
      ResetRelease()

    steps = {
      0 : Step0,
      1 : Step1,
      2 : Step2,
      3 : Step3,
      4 : Step4,
      5 : Step5,
      6 : Step6,
      7 : Step7,
      8 : Step8,
      9 : Step9,
      10: Step10,
      11: Step11,
    }

    steps[state]()


def ResetRelease():
  os.remove(_ShelveLocation())


def _ShelveLocation():
  return path.join(path.expanduser('~'), '.spoofax-releng-release-state')

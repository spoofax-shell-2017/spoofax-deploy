import shelve
import os
import git
import traceback

from os import path
from metaborg.util.git import CheckoutAll, UpdateAll
from metaborg.util.prompt import YesNo


def Release(repo, releaseBranchName, developBranchName, curReleaseVersion, curDevelopVersion, nextReleaseVersion, nextDevelopVersion):
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
      submoduleBranches = {}
      for submodule in repo.submodules:
        submoduleBranches[submodule.name] = submodule.branch
      db['submoduleBranches'] = submoduleBranches
      db['state'] = 1
      Step1()

    def Step1():
      print('Step 1: prepare release branch')
      releaseBranch.checkout()
      CheckoutAll(repo)
      repo.remotes.origin.pull()
      UpdateAll(repo)
      db['state'] = 2
      Step2()

    def Step2():
      print('Step 2: merge development branch into release branch')
      try:
        repo.git.merge(developBranch.name)
      except git.exc.GitCommandError as detail:
        print('Automatic merge failed')
        print(str(detail))
      db['state'] = 3
      print('Please fix any conflicts and commit all changes in the root repository, then continue')

    def Step3():
      if repo.is_dirty():
        print('You have uncommited changes, are you sure you want to continue?')
        if not YesNo():
          return
      print('Step 3: for each submodule: merge development branch into release branch')
      submoduleBranches = db['submoduleBranches']
      for submodule in repo.submodules:
        subrepo = submodule.module()
        try:
          subrepo.git.merge(submoduleBranches[submodule.name])
        except git.exc.GitCommandError as detail:
          print('Automatic merge failed')
          print(str(detail))
      #db['state'] = 4
      print('Please fix any conflicts and commit all changes in all submodules, then continue')

    def Step4():
      # for each submodule, check status of repository: no conflicts, no uncommited changes
      # if bad status: inform user and stop
      print('Step 4: for each submodule: set version from the current development version to the next release version')
      # set version from current development version to next release version
      #db['state'] = 5
      print('Please check if versions have been set correctly, then continue')

    def Step5():
      print('Step 5: perform a test release build')
      # perform a release build
      # if it fails: inform user and stop
      #db['state'] = 6
      print('Please check if the built artifact works, then continue')

    def Step6():
      print('Step 6: perform release deployment')
      # perform a release deploy
      #db['state'] = 7
      print('Please check if deploying succeeded, and manually deploy extra artifacts, then continue')

    def Step7():
      print('Step 7: push repository and submodules')
      # push all commits in repo and submodules
      #db['state'] = 8
      Step8()

    def Step8():
      print('Step 8: switch to development branch')
      # switch to development branch
      #db['state'] = 9
      Step9()

    def Step9():
      print('Step 9: for each submodule: set version from the current development version to the next development version')
      # switch to development branch
      # set version from current development version to next development version
      #db['state'] = 10
      print('Please check if versions have been set correctly, then continue')

    def Step10():
      print('Step 10: push repository and submodules')
      # push all commits in submodules
      print('All done!')
      #ResetRelease()

    steps = {
       0 :  Step0,
       1 :  Step1,
       2 :  Step2,
       3 :  Step3,
       4 :  Step4,
       5 :  Step5,
       6 :  Step6,
       7 :  Step7,
       8 :  Step8,
       9 :  Step9,
      10 : Step10,
    }

    steps[state]()

def ResetRelease():
  os.remove(_ShelveLocation())

def _ShelveLocation():
  return path.join(path.expanduser('~'), '.spoofax-releng-state')
import os
import shelve
from os import path

import git

from metaborg.releng.build import RelengBuilder
from metaborg.releng.versions import SetVersions
from metaborg.util.git import CheckoutAll, UpdateAll, TagAll, PushAll
from metaborg.util.prompt import YesNo


class MetaborgRelease(object):
  def __init__(self, repo, releaseBranchName, nextReleaseVersion, developBranchName, curDevelopVersion, deployKind):
    self.repo = repo
    self.releaseBranchName = releaseBranchName
    self.nextReleaseVersion = nextReleaseVersion
    self.developBranchName = developBranchName
    self.curDevelopVersion = curDevelopVersion
    self.deployKind = deployKind

    self.nextDevelopVersion = None

    self.interactive = True

    self.bootstrapStratego = False
    self.testStratego = False

    self.bintrayUsername = None
    self.bintrayKey = None

  def release(self):
    with shelve.open(MetaborgRelease.__shelve_location()) as db:
      releaseBranch = self.repo.heads[self.releaseBranchName]
      developBranch = self.repo.heads[self.developBranchName]

      if 'state' in db:
        state = db['state']
      else:
        state = 0

      def Step0():
        print('Step 0: prepare development branch')
        developBranch.checkout()
        CheckoutAll(self.repo)
        self.repo.remotes.origin.pull()
        CheckoutAll(self.repo)  # Check out again in case .gitmodules was changed.
        UpdateAll(self.repo)
        submoduleDevBranches = {}
        for submodule in self.repo.submodules:
          submoduleDevBranches[submodule.name] = submodule.branch
        db['submoduleDevBranches'] = submoduleDevBranches
        db['state'] = 1
        Step1()

      def Step1():
        print('Step 1: prepare release branch')
        releaseBranch.checkout()
        CheckoutAll(self.repo)
        self.repo.remotes.origin.pull()
        CheckoutAll(self.repo)  # Check out again in case .gitmodules was changed.
        UpdateAll(self.repo)
        submoduleRelBranches = {}
        for submodule in self.repo.submodules:
          submoduleRelBranches[submodule.name] = submodule.branch
        db['submoduleRelBranches'] = submoduleRelBranches
        db['state'] = 2
        Step2()

      def Step2():
        print('Step 2: merge development branch into release branch')
        try:
          # Merge using 'theirs' to overwrite any changes in the release branch with changes from the development branch
          self.repo.git.merge('--strategy=recursive', '--strategy-option=theirs', developBranch.name)
        except git.exc.GitCommandError as detail:
          print('Automatic merge failed')
          print(str(detail))
          if not self.interactive:
            raise Exception('Error while in non-interactive mode, stopping')
        try:
          # Restore .gitmodules because the submodule branches should not be overwritten by the development branch
          self.repo.git.checkout('--ours', '--', '.gitmodules')
        except git.exc.GitCommandError as detail:
          print("Restoring '.gitmodules' file failed")
          print(str(detail))
          if not self.interactive:
            raise Exception('Error while in non-interactive mode, stopping')
        db['state'] = 3
        print('Please fix any conflicts and commit all changes in the root repository, then continue')

      def Step3():
        if self.repo.is_dirty():
          print('You have uncommitted changes, are you sure you want to continue?')
          if not YesNo():
            return
        print('Step 3: for each submodule: merge development branch into release branch')
        submoduleDevBranches = db['submoduleDevBranches']
        submoduleRelBranches = db['submoduleRelBranches']
        for submodule in self.repo.submodules:
          subrepo = submodule.module()
          try:
            if not submodule.name in submoduleDevBranches:
              print('Submodule {} does not have a development branch, assuming {}'.format(submodule.name,
                self.developBranchName))
              submoduleDevBranch = self.developBranchName
            else:
              submoduleDevBranch = submoduleDevBranches[submodule.name]

            if not submodule.name in submoduleRelBranches:
              print('Submodule {} does not have a release branch, assuming {}'.format(submodule.name,
                self.releaseBranchName))
              submoduleRelBranch = self.releaseBranchName
            else:
              submoduleRelBranch = submoduleRelBranches[submodule.name]

            print('Merging submodule {}'.format(submodule.name))
            # Use merging strategy 3 from http://stackoverflow.com/a/27338013/499240 to make release branch identical to
            # development branch, while keeping correct parent order.
            subrepo.git.merge('--strategy=ours', submoduleDevBranch)
            subrepo.git.checkout('--detach', submoduleDevBranch)
            subrepo.git.reset('--soft', submoduleRelBranch)
            subrepo.git.checkout(submoduleRelBranch)
            subrepo.git.commit('--amend', '-C', 'HEAD')
          except git.exc.GitCommandError as detail:
            print('Automatic merge failed')
            print(str(detail))
            if not self.interactive:
              raise Exception('Error while in non-interactive mode, stopping')
        db['state'] = 4
        print('Please fix any conflicts and commit all changes in all submodules, then continue')

      def Step4():
        dirtyRepos = []
        for submodule in self.repo.submodules:
          subrepo = submodule.module()
          if subrepo.is_dirty():
            dirtyRepos.append(submodule.name)
        if len(dirtyRepos) > 0:
          print('You have uncommitted changes in submodules {}.'.format(dirtyRepos))
          if not self.interactive:
            raise Exception('Error while in non-interactive mode, stopping')
          print('Are you sure you want to continue?')
          if not YesNo():
            return
        print('Step 4: for each submodule: set version from the current development version to the next release version')
        SetVersions(self.repo, self.curDevelopVersion, self.nextReleaseVersion, setEclipseVersions=True, dryRun=False,
          commit=True)
        print('Updating submodule revisions')
        self.repo.git.add('--all')
        self.repo.index.commit('Update submodule revisions')
        db['state'] = 5
        print('Please check if versions have been set correctly, then continue')

      def Step5():
        print('Step 5: build and deploy')
        builder = RelengBuilder(self.repo)
        # builder = RelengBuilder(self.repo, buildDeps=False)
        builder.deployKind = self.deployKind
        builder.buildStratego = True
        builder.bootstrapStratego = self.bootstrapStratego
        builder.testStratego = self.testStratego
        builder.bintrayUsername = self.bintrayUsername
        builder.bintrayKey = self.bintrayKey
        builder.bintrayVersion = self.nextReleaseVersion
        try:
          builder.build('all', 'eclipse-instances')
          # builder.build('poms', 'jars', 'java')
        except Exception as detail:
          print('Build and deploy failed, not continuing to the next step')
          print(str(detail))
          if not self.interactive:
            raise Exception('Error while in non-interactive mode, stopping')
          return
        db['state'] = 7
        print('Please check if building and deploying succeeded, then continue')

      def Step7():
        print('Step 7: tag release submodules and repository')
        tagName = '{}/{}'.format(self.releaseBranchName, self.nextReleaseVersion)
        tagDescription = 'Tag for {} release'.format(self.nextReleaseVersion)
        TagAll(self.repo, tagName, tagDescription)
        print('Creating tag {}'.format(tagName))
        self.repo.create_tag(path=tagName, message=tagDescription)
        db['state'] = 8
        Step8()

      def Step8():
        print('Step 8: push release submodules and repository')
        PushAll(self.repo)
        PushAll(self.repo, tags=True)
        print('Pushing')
        remote = self.repo.remote('origin')
        remote.push()
        remote.push(tags=True)
        db['state'] = 9
        Step9()

      def Step9():
        print('Step 9: switch to development branch')
        developBranch.checkout()
        CheckoutAll(self.repo)
        db['state'] = 10
        Step10()

      def Step10():
        if self.nextDevelopVersion:
          print(
            'Step 10: for each submodule: set version from the current development version to the next development version')
          SetVersions(self.repo, self.curDevelopVersion, self.nextDevelopVersion, setEclipseVersions=True, dryRun=False,
            commit=True)
          print('Updating submodule revisions')
          self.repo.git.add('--all')
          self.repo.index.commit('Update submodule revisions')
          print('Please check if versions have been set correctly, then continue')
        else:
          print('Step 10: skipping, no next development version has been set')
        db['state'] = 11

      def Step11():
        print('Step 11: push development submodules and repository')
        PushAll(self.repo)
        print('Pushing')
        remote = self.repo.remote('origin')
        remote.push()
        print('All done!')
        self.reset()

      steps = {
        0 : Step0,
        1 : Step1,
        2 : Step2,
        3 : Step3,
        4 : Step4,
        5 : Step5,
        7 : Step7,
        8 : Step8,
        9 : Step9,
        10: Step10,
        11: Step11,
      }

      steps[state]()

  # noinspection PyMethodMayBeStatic
  def reset(self):
    os.remove(MetaborgRelease.__shelve_location())

  @staticmethod
  def __shelve_location():
    return path.join(path.expanduser('~'), '.spoofax-releng-release-state')

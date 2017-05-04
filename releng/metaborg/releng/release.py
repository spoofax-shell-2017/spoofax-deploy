import os
import shelve
from os import path

import git

from metaborg.releng.versions import SetVersions
from metaborg.util.git import CheckoutAll, UpdateAll, TagAll, PushAll
from metaborg.util.prompt import YesNo


class MetaborgRelease(object):
  def __init__(self, repo, releaseBranchName, nextReleaseVersion, developBranchName, curDevelopVersion, builder):
    self.repo = repo
    self.releaseBranchName = releaseBranchName
    self.nextReleaseVersion = nextReleaseVersion
    self.developBranchName = developBranchName
    self.curDevelopVersion = curDevelopVersion
    self.builder = builder

    self.nextDevelopVersion = None
    self.createEclipseInstances = True

    self.dryRun = False
    self.interactive = True

  def release(self):
    with shelve.open(self.__shelve_location()) as db:
      releaseBranch = self.repo.heads[self.releaseBranchName]
      developBranch = self.repo.heads[self.developBranchName]

      if 'state' in db:
        state = db['state']
      else:
        state = 0

      def Step0():
        print('Step 0: prepare development branch')

        try:
          developBranch.checkout()
          CheckoutAll(self.repo)
          self.repo.remotes.origin.pull()
          CheckoutAll(self.repo)  # Check out again in case .gitmodules was changed.
          UpdateAll(self.repo)
        except git.exc.GitCommandError as detail:
          print('ERROR: preparing development branch failed')
          print(str(detail))
          if not self.interactive:
            raise Exception('Error while in non-interactive mode, stopping')
          return

        submoduleDevBranches = {}
        for submodule in self.repo.submodules:
          submoduleDevBranches[submodule.name] = submodule.branch
        db['submoduleDevBranches'] = submoduleDevBranches

        db['state'] = 1
        Step1()

      def Step1():
        print('Step 1: prepare release branch')

        try:
          releaseBranch.checkout()
          CheckoutAll(self.repo)
          self.repo.remotes.origin.pull()
          CheckoutAll(self.repo)  # Check out again in case .gitmodules was changed.
          UpdateAll(self.repo)
        except git.exc.GitCommandError as detail:
          print('ERROR: preparing release branch failed')
          print(str(detail))
          if not self.interactive:
            raise Exception('Error while in non-interactive mode, stopping')
          return

        submoduleRelBranches = {}
        for submodule in self.repo.submodules:
          submoduleRelBranches[submodule.name] = submodule.branch
        db['submoduleRelBranches'] = submoduleRelBranches

        db['state'] = 2
        Step2()

      def Step2():
        print('Step 2: merge development branch into release branch')

        print('Merging branch {}'.format(self.developBranchName))
        try:
          # Use merging strategy 3 from http://stackoverflow.com/a/27338013/499240 to make release branch identical to
          # development branch, while keeping correct parent order. Commit is done after restoring .gitmodules file.
          self.repo.git.merge('--strategy=ours', self.developBranchName)
          self.repo.git.checkout('--detach', self.developBranchName)
          self.repo.git.reset('--soft', self.releaseBranchName)
          self.repo.git.checkout(self.releaseBranchName)
        except git.exc.GitCommandError as detail:
          print('ERROR: automatic merge failed')
          print(str(detail))
          if not self.interactive:
            raise Exception('Error while in non-interactive mode, stopping')

        # Restore changes that should not be merged
        print('Restoring changes that should not be merged')
        try:
          self.repo.git.checkout(self.releaseBranchName, '--', '.gitmodules')
          self.repo.git.checkout(self.releaseBranchName, '--', 'build.properties')
          self.repo.git.checkout(self.releaseBranchName, '--', 'jenkins.properties')
        except git.exc.GitCommandError as detail:
          print('ERROR: restoring changes that should not be merged failed')
          print(str(detail))
          if not self.interactive:
            raise Exception('Error while in non-interactive mode, stopping')

        print('Committing merge')
        try:
          self.repo.git.add('--all')
          self.repo.git.commit('--amend', '--allow-empty', '-C', 'HEAD')
        except git.exc.GitCommandError as detail:
          print('ERROR: committing merge failed')
          print(str(detail))
          if not self.interactive:
            raise Exception('Error while in non-interactive mode, stopping')

        db['state'] = 3
        if self.interactive:
          print('Please fix any conflicts and commit all changes (if any) in the root repository, then continue')
        else:
          Step3()

      def Step3():
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

            print('Merging branch {} into submodule {}'.format(submoduleDevBranch, submodule.name))
            # Use merging strategy 3 from http://stackoverflow.com/a/27338013/499240 to make release branch identical to
            # development branch, while keeping correct parent order.
            subrepo.git.merge('--strategy=ours', submoduleDevBranch)
            subrepo.git.checkout('--detach', submoduleDevBranch)
            subrepo.git.reset('--soft', submoduleRelBranch)
            subrepo.git.checkout(submoduleRelBranch)
            subrepo.git.add('--all')
            subrepo.git.commit('--amend', '--allow-empty', '-C', 'HEAD')
          except git.exc.GitCommandError as detail:
            print('ERROR: automatic merge failed')
            print(str(detail))
            if not self.interactive:
              raise Exception('Error while in non-interactive mode, stopping')
        db['state'] = 4

        if self.interactive:
          print('Please fix any conflicts and commit all changes (if any) in all submodules, then continue')
        else:
          Step4()

      def Step4():
        dirtyRepos = []
        for submodule in self.repo.submodules:
          subrepo = submodule.module()
          if subrepo.is_dirty():
            dirtyRepos.append(submodule.name)
        if len(dirtyRepos) > 0:
          print('ERROR: uncommitted changes in submodules {}'.format(dirtyRepos))
          if not self.interactive:
            raise Exception('Error while in non-interactive mode, stopping')
          print('Are you sure you want to continue?')
          if not YesNo():
            return

        print(
          'Step 4: for each submodule: set version from the current development version to the next release version')

        print('Setting versions')
        try:
          SetVersions(self.repo, self.curDevelopVersion, self.nextReleaseVersion, dryRun=False, commit=True)
        except Exception as detail:
          print('ERROR: Setting versions failed')
          print(str(detail))
          if not self.interactive:
            raise Exception('Error while in non-interactive mode, stopping')

        print('Updating submodule revisions')
        try:
          self.repo.git.add('--all')
          self.repo.index.commit('Update submodule revisions')
        except git.exc.GitCommandError as detail:
          print('ERROR: updating submodule revisions failed')
          print(str(detail))
          if not self.interactive:
            raise Exception('Error while in non-interactive mode, stopping')

        db['state'] = 5
        if self.interactive:
          print('Please check if versions have been set correctly, then continue')
        else:
          Step5()

      def Step5():
        print('Step 5: build and deploy')

        builder = self.builder
        builder.buildStratego = True
        try:
          if self.createEclipseInstances:
            builder.build('all', 'eclipse-instances')
          else:
            builder.build('all')
        except Exception as detail:
          print('ERROR: build and deploy failed')
          print(str(detail))
          if not self.interactive:
            raise Exception('Error while in non-interactive mode, stopping')
          return

        db['state'] = 7
        if self.interactive:
          print('Please check if building and deploying succeeded, then continue')
        else:
          Step7()

      def Step7():
        print('Step 7: tag release submodules and repository')

        tagName = '{}/{}'.format(self.releaseBranchName, self.nextReleaseVersion)
        tagDescription = 'Tag for {} release'.format(self.nextReleaseVersion)

        print('Creating tag {}'.format(tagName))
        try:
          TagAll(self.repo, tagName, tagDescription)
          self.repo.create_tag(path=tagName, message=tagDescription)
        except git.exc.GitCommandError as detail:
          print('ERROR: creating tag failed')
          print(str(detail))
          if not self.interactive:
            raise Exception('Error while in non-interactive mode, stopping')
          return

        db['state'] = 8
        Step8()

      def Step8():
        print('Step 8: push release submodules and repository')

        try:
          if not self.dryRun:
            print('Pushing changes')
            PushAll(self.repo)
            PushAll(self.repo, tags=True)
            remote = self.repo.remote('origin')
            remote.push()
            remote.push(tags=True)
          else:
            print('Performing dry run, not pushing')
        except git.exc.GitCommandError as detail:
          print('ERROR: pushing changes failed')
          print(str(detail))
          if not self.interactive:
            raise Exception('Error while in non-interactive mode, stopping')
          return

        db['state'] = 9
        Step9()

      def Step9():
        print('Step 9: switch to development branch')

        try:
          developBranch.checkout()
          CheckoutAll(self.repo)
        except git.exc.GitCommandError as detail:
          print('ERROR: switching to development branch failed')
          print(str(detail))
          if not self.interactive:
            raise Exception('Error while in non-interactive mode, stopping')
          return

        db['state'] = 10
        Step10()

      def Step10():
        if self.nextDevelopVersion:
          print(
            'Step 10: for each submodule: set version from the current development version to the next development version')

          print('Setting versions')
          SetVersions(self.repo, self.curDevelopVersion, self.nextDevelopVersion, dryRun=False, commit=True)

          print('Updating submodule revisions')
          try:
            self.repo.git.add('--all')
            self.repo.index.commit('Update submodule revisions')
          except git.exc.GitCommandError as detail:
            print('ERROR: updating submodule revisions failed')
            print(str(detail))
            if not self.interactive:
              raise Exception('Error while in non-interactive mode, stopping')
            return

          if self.interactive:
            print('Please check if versions have been set correctly, then continue')
        else:
          print('Step 10: skipping, no next development version has been set')

        db['state'] = 11
        if not self.interactive:
          Step11()

      def Step11():
        print('Step 11: push development submodules and repository')

        try:
          if not self.dryRun:
            print('Pushing changes')
            PushAll(self.repo)
            remote = self.repo.remote('origin')
            remote.push()
          else:
            print('Performing dry run, not pushing')
        except git.exc.GitCommandError as detail:
          print('ERROR: pushing changes failed')
          print(str(detail))
          if not self.interactive:
            raise Exception('Error while in non-interactive mode, stopping')
          return

        print('DONE')
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

  def revert(self):
    def resetRepo(repo, name):
      head = repo.head
      remote = repo.remote()
      branchName = '{}/{}'.format(remote.name, head.reference.name)
      try:
        print('Reverting {} to {}'.format(name, branchName))
        repo.git.reset('--hard', branchName)
        repo.git.clean('-ddffxx')
      except git.exc.GitCommandError as detail:
        print('Could not revert {} to {}'.format(name, branchName))
        print(detail)

    releaseBranch = self.repo.heads[self.releaseBranchName]
    releaseBranch.checkout()
    CheckoutAll(self.repo)
    for submodule in self.repo.submodules:
      module = submodule.module()
      resetRepo(module, submodule.name)
    resetRepo(self.repo, 'root')

    developBranch = self.repo.heads[self.developBranchName]
    developBranch.checkout()
    CheckoutAll(self.repo)
    for submodule in self.repo.submodules:
      module = submodule.module()
      resetRepo(module, submodule.name)
    resetRepo(self.repo, 'root')

  def reset(self):
    location = self.__shelve_location()
    if os.path.isfile(location):
      os.remove(location)

  def __shelve_location(self):
    return path.join(path.expanduser('~'), '.spoofax-releng-release-state')

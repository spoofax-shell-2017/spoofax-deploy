import datetime
import os
import re
import time
from enum import Enum, unique


def LatestDate(repo):
  date = 0
  for submodule in repo.submodules:
    subrepo = submodule.module()
    head = subrepo.head
    if head.is_detached:
      commitDate = head.commit.committed_date
    else:
      commitDate = head.ref.commit.committed_date

    if commitDate > date:
      date = commitDate

  return datetime.datetime.fromtimestamp(date)


def Branch(repo):
  head = repo.head
  if head.is_detached:
    return "DETACHED"
  return head.reference.name


def Fetch(submodule):
  if not submodule.module_exists():
    return
  print('Fetching {}'.format(submodule.name))
  subrepo = submodule.module()
  subrepo.git.fetch()


def FetchAll(repo):
  for submodule in repo.submodules:
    Fetch(submodule)


def Update(repo, submodule, remote=True, recursive=True, depth=None):
  args = ['update', '--init']

  if recursive:
    args.append('--recursive')
  if remote:
    args.append('--remote')
  if depth:
    args.append('--depth')
    args.append(depth)

  if not submodule.module_exists():
    print('Initializing {}'.format(submodule.name))
  else:
    subrepo = submodule.module()
    remote = subrepo.remote()
    head = subrepo.head
    if head.is_detached:
      print('Updating {}'.format(submodule.name))
    else:
      args.append('--rebase')
      print('Updating {} from {}/{}'.format(submodule.name, remote.name, head.reference.name))

  args.append('--')
  args.append(submodule.name)

  repo.git.submodule(args)


def UpdateAll(repo, remote=True, recursive=True, depth=None):
  for submodule in repo.submodules:
    Update(repo, submodule, remote=remote, recursive=recursive, depth=depth)


def Checkout(repo, submodule):
  if not submodule.module_exists():
    Update(repo, submodule)

  branch = submodule.branch
  print('Switching {} to {}'.format(submodule.name, branch.name))
  branch.checkout()

  if not submodule.module_exists():
    print('Cannot recursively checkout, {} has not been initialized yet.'.format(submodule.name))
    return

  subrepo = submodule.module()
  for submodule in subrepo.submodules:
    Checkout(subrepo, submodule)


def CheckoutAll(repo):
  for submodule in repo.submodules:
    Checkout(repo, submodule)


def Clean(submodule):
  if not submodule.module_exists():
    print('Cannot clean, {} has not been initialized yet.'.format(submodule.name))
    return

  subrepo = submodule.module()
  print('Cleaning {}'.format(submodule.name))
  subrepo.git.clean('-dfx', '-e', '.project', '-e', '.classpath', '-e', '.settings', '-e', 'META-INF')


def CleanAll(repo):
  for submodule in repo.submodules:
    Clean(submodule)


def Reset(submodule, toRemote):
  if not submodule.module_exists():
    print('Cannot reset, {} has not been initialized yet.'.format(submodule.name))
    return

  subrepo = submodule.module()
  if toRemote:
    head = subrepo.head
    if head.is_detached:
      print('Cannot reset, {} has a DETACHED HEAD.'.format(submodule.name))
      return
    remote = subrepo.remote()
    branchName = '{}/{}'.format(remote.name, head.reference.name)
    print('Resetting {} to {}'.format(submodule.name, branchName))
    subrepo.git.reset('--hard', branchName)
  else:
    print('Resetting {}'.format(submodule.name))
    subrepo.git.reset('--hard')


def ResetAll(repo, toRemote):
  for submodule in repo.submodules:
    Reset(submodule, toRemote)


def Merge(submodule, branchName):
  if not submodule.module_exists():
    print('Cannot merge, {} has not been initialized yet.'.format(submodule.name))
    return

  subrepo = submodule.module()
  subrepo.git.merge(branchName)


def MergeAll(repo, branchName):
  for submodule in repo.submodules:
    Merge(submodule, branchName)


def Tag(submodule, tagName, tagDescription):
  if not submodule.module_exists():
    print('Cannot tag, {} has not been initialized yet.'.format(submodule.name))
    return

  print('Creating tag {} in {}'.format(tagName, submodule.name))
  subrepo = submodule.module()
  subrepo.create_tag(path=tagName, message=tagDescription)


def TagAll(repo, tagName, tagDescription):
  for submodule in repo.submodules:
    Tag(submodule, tagName, tagDescription)


def Push(submodule, **kwargs):
  if not submodule.module_exists():
    print('Cannot push, {} has not been initialized yet.'.format(submodule.name))
    return

  print('Pushing {}'.format(submodule.name))
  subrepo = submodule.module()
  remote = subrepo.remote()
  remote.push(**kwargs)


def PushAll(repo, **kwargs):
  for submodule in repo.submodules:
    Push(submodule, **kwargs)


def Track(submodule):
  if not submodule.module_exists():
    print('Cannot set tracking branch, {} has not been initialized yet.'.format(submodule.name))
    return

  subrepo = submodule.module()
  head = subrepo.head
  remote = subrepo.remote()
  localBranchName = head.reference.name
  remoteBranchName = '{}/{}'.format(remote.name, localBranchName)
  print('Setting tracking branch for {} to {}'.format(localBranchName, remoteBranchName))
  subrepo.git.branch('-u', remoteBranchName, localBranchName)


def TrackAll(repo):
  for submodule in repo.submodules:
    Track(submodule)


@unique
class RemoteType(Enum):
  SSH = 1
  HTTP = 2


def SetRemoteAll(repo, toType=RemoteType.SSH):
  for submodule in repo.submodules:
    SetRemote(submodule, toType)


def SetRemote(submodule, toType):
  if not submodule.module_exists():
    print('Cannot set remote, {} has not been initialized yet.'.format(submodule.name))
    return
  name = submodule.name
  subrepo = submodule.module()
  origin = subrepo.remote()
  currentUrl = origin.config_reader.get('url')

  httpMatch = re.match('https?://([\w\.@:\-~]+)/(.+)', currentUrl)
  sshMatch = re.match('(?:ssh://)?([\w\.@\-~]+)@([\w\.@\-~]+)[:/](.+)', currentUrl)
  if httpMatch:
    user = 'git'
    host = httpMatch.group(1)
    path = httpMatch.group(2)
  elif sshMatch:
    user = sshMatch.group(1)
    host = sshMatch.group(2)
    path = sshMatch.group(3)
  else:
    raise RuntimeError('Cannot set remote for {}, unknown URL format {}.'.format(name, currentUrl))

  if toType is RemoteType.SSH:
    newUrl = '{}@{}:{}'.format(user, host, path)
  elif toType is RemoteType.HTTP:
    newUrl = 'https://{}/{}'.format(host, path)
  else:
    raise RuntimeError('Cannot set remote for {}, unknown URL type {}.'.format(name, str(toType)))

  print('Setting remote for {} to {}'.format(name, newUrl))
  origin.config_writer.set('url', newUrl)


def create_qualifier(repo, branch=None):
  timestamp = LatestDate(repo)
  if not branch:
    branch = Branch(repo)
  return _format_qualifier(timestamp, branch)


def create_now_qualifier(repo, branch=None):
  timestamp = datetime.datetime.now()
  if not branch:
    branch = Branch(repo)
  return _format_qualifier(timestamp, branch)


def _format_qualifier(timestamp, branch):
  return '{}-{}'.format(timestamp.strftime('%Y%m%d-%H%M%S'), branch.replace('/', '_'))


def repo_changed(repo, qualifierLocation):
  timestamp = LatestDate(repo)
  branch = Branch(repo)
  changed = False
  if not os.path.isfile(qualifierLocation):
    changed = True
  else:
    with open(qualifierLocation, mode='r') as qualifierFile:
      storedTimestampStr = qualifierFile.readline().replace('\n', '')
      storedBranch = qualifierFile.readline().replace('\n', '')
      if not storedTimestampStr or not storedBranch:
        raise RuntimeError('Invalid qualifier file {}, please delete this file and retry'.format(qualifierLocation))
      storedTimestamp = datetime.datetime.fromtimestamp(int(storedTimestampStr))
      changed = (timestamp > storedTimestamp) or (branch != storedBranch)
  with open(qualifierLocation, mode='w') as timestampFile:
    timestampStr = str(int(time.mktime(timestamp.timetuple())))
    timestampFile.write('{}\n{}\n'.format(timestampStr, branch))
  return changed, _format_qualifier(timestamp, branch)

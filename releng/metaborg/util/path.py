from itertools import takewhile


def CommonPrefix(paths, sep='/'):
  """
  Finds the common path prefix in given list of paths.
  The os.path.commonprefix function is broken, since it finds prefixes on the character level, not the path level.
  From: http://rosettacode.org/wiki/Find_Common_Directory_Path#Python
  """
  byDirectoryLevels = zip(*[p.split(sep) for p in paths])

  def AllNamesEqual(name):
    return all(n == name[0] for n in name[1:])

  return sep.join(x[0] for x in takewhile(AllNamesEqual, byDirectoryLevels))

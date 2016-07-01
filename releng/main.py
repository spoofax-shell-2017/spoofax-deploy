from metaborg.releng.cmd import MetaborgReleng

if __name__ == "__main__":
  try:
    MetaborgReleng.run()
  except KeyboardInterrupt as detail:
    print(detail)

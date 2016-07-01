def GenerateIcons(repo, destination_dir, text=''):
  from metaborg.util.icons import IconGenerator, ensure_directory_exists

  basedir = repo.working_tree_dir
  source_dir = '{}/spoofax/graphics/icons'.format(basedir)
  ensure_directory_exists(destination_dir)
  gen = IconGenerator('{}/spoofax/graphics/fonts/kadwa/Kadwa Font Files/Kadwa-Regular.otf'.format(basedir))
  for source_name in ['spoofax']:
    print('Generating icons for {} '.format(source_name))
    destination_name = source_name
    gen.generate_pngs(source_dir, source_name, destination_dir, destination_name, text)
    gen.generate_ico(source_dir, source_name, destination_dir, destination_name, text)
    # gen.generate_icns(source_dir, source_name, destination_dir, destination_name, text)

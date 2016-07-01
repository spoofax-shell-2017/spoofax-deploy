import os.path
import sys

try:
  from wand.image import Image
  from wand.color import Color
  from wand.drawing import Drawing

  wand_available = True
except ImportError:
  wand_available = False


def assert_wand_available():
  if not wand_available:
    raise ImportError('MagickWand shared library not found.\n'
                      'You probably had not installed ImageMagick library.\n')


class IconGenerator:
  __ALL_SIZES = [16, 32, 48, 64, 128, 256, 512, 1024]
  __ICO_SIZES = [16, 32, 48, 64, 128, 256]
  __ICNS_SIZES = [16, 32, 48, 128, 256, 512, 1024]

  def __init__(self, font):
    """
    Initializes the IconGenerator class.

    :type font: basestring
    :param font: Path of font to use.
    """
    assert_wand_available()

    self.font = font

  def generate_pngs(self, source_dir, source_name, destination_dir, destination_name, text=''):
    """
    Generates all PNG files.

    :type source_dir: basestring
    :param source_dir: The source directory.
    :type source_name: basestring
    :param source_name: The source name, without directory or extension.
    :type destination_dir: basestring
    :param destination_dir: The destination directory.
    :type destination_name: basestring
    :param destination_name: The destination name, without directory or extension.
    :type text: basestring
    :param text: The text to display on the icon. Default: empty string.
    :rtype: list of basestring
    :return: Paths to the resulting files.
    """
    destination_paths = []
    for size in self.__ALL_SIZES:
      destination_path = self.generate_png(source_dir, source_name, destination_dir, destination_name, size, text)
      destination_paths.append(destination_path)
    return destination_paths

  def generate_png(self, source_dir, source_name, destination_dir, destination_name, size, text=''):
    """
    Generates a PNG file.

    :type source_dir: basestring
    :param source_dir: The source directory.
    :type source_name: basestring
    :param source_name: The source name, without directory or extension.
    :type destination_dir: basestring
    :param destination_dir: The destination directory.
    :type destination_name: basestring
    :param destination_name: The destination name, without directory or extension.
    :type size: int
    :param size: The size of the icon.
    :type text: basestring
    :param text: The text to display on the icon. Default: empty string.
    :rtype: basestring
    :return: Path to the resulting file.
    """
    destination_path = '{}/{}_{}.png'.format(destination_dir, destination_name, size)
    with self.load_icon_source(source_dir, source_name, size) as source:
      with self.draw_icon(source, size, text) as drawn:
        drawn.format = "png"
        drawn.save(filename=destination_path)
    return destination_path

  def generate_ico(self, source_dir, source_name, destination_dir, destination_name, text=''):
    """
    Generates a Windows ICO file.

    :type source_dir: basestring
    :param source_dir: The source directory.
    :type source_name: basestring
    :param source_name: The source name, without directory or extension.
    :type destination_dir: basestring
    :param destination_dir: The destination directory.
    :type destination_name: basestring
    :param destination_name: The destination name, without directory or extension.
    :type text: basestring
    :param text: The text to display on the icon. Default: empty string.
    :rtype: basestring
    :return: Path to the resulting file.
    """
    destination_path = '{}/{}.ico'.format(destination_dir, destination_name)
    source_files = [(self.load_icon_source(source_dir, source_name, size), size) for size in self.__ICO_SIZES]
    drawn_files = [self.draw_icon(img, size, text) for (img, size) in source_files]
    with Image(format='ico') as ico:
      for drawn in drawn_files:
        ico.sequence.append(drawn)
      ico.save(filename=destination_path)
    for drawn in drawn_files:
      drawn.close()
    for (source, _) in source_files:
      source.close()
    return destination_path

  def generate_icns(self, source_dir, source_name, destination_dir, destination_name, text=''):
    """
    Generates a Mac ICNS file.

    :type source_dir: basestring
    :param source_dir: The source directory.
    :type source_name: basestring
    :param source_name: The source name, without directory or extension.
    :type destination_dir: basestring
    :param destination_dir: The destination directory.
    :type destination_name: basestring
    :param destination_name: The destination name, without directory or extension.
    :type text: basestring
    :param text: The text to display on the icon. Default: empty string.
    :rtype: basestring
    :return: Path to the resulting file.
    """
    destination_path = '{}/{}.icns'.format(destination_dir, destination_name)
    source_files = [(self.load_icon_source(source_dir, source_name, size), size) for size in self.__ICNS_SIZES]
    drawn_files = [self.draw_icon(img, size, text) for (img, size) in source_files]
    # TODO: Write all drawn_files to temporary files
    # and provide them as args to the png2icns subprocess.
    # input_files = [self.get_destination_sized_file(destination_dir, destination_name, x, '.png') for x in input_sizes]
    # subprocess.call(['png2icns', destination_file] + input_files)
    raise Exception('Not implemented!')

  def load_icon_source(self, source_dir, source_name, size=sys.maxsize):
    """
    Loads a source image. The source files should be in `source_name`
    and their names should have the following format: `<source_name>_<size>.svg`

    When no source image of the specified size can be found, the next bigger
    source image is used. If no such source image can be found, the next smaller
    source image is used. If no such source image can be found, an exception is thrown.

    **Note**: This method returns an `Image` object on which you have to call `close()`,
    or use it in a `with` statement.

    :type source_dir: basestring
    :param source_dir: The source directory.
    :type source_name: basestring
    :param source_name: The source name, without the path, size or extension.
    :type size: int
    :param size: The preferred size of the source.
    :rtype: Image
    :return: The loaded source image.
    """

    sizes = [x for x in self.__ALL_SIZES if x == size] \
            + [x for x in self.__ALL_SIZES if x > size] \
            + [x for x in self.__ALL_SIZES if x < size]
    for x in sizes:
      path = '{}/{}_{}.svg'.format(source_dir, source_name, x)
      if os.path.isfile(path):
        return Image(filename=path)
    raise Exception("Source files '{}/{}_*.svg' not found.".format(source_dir, source_name))

  def draw_icon(self, source, size, text=''):
    """
    Draws an icon of the specified size from the specified source image.

    **Note**: This method returns an `Image` object on which you have to call `close()`,
    or use it in a `with` statement.

    :type source: Image
    :param source: The source image.
    :type size: int
    :param size: The size of the icon, in pixels.
    :type text: basestring
    :param text: The text to display on the icon.
    :rtype: Image
    :return: The resulting image.
    """

    img = source.clone()
    img.resize(size, size)
    self.__draw_text_bottom_left(img, text)
    return img

  __TEXT_PARAMS = {
    16  : {'font_stroke': 0, 'font_size': 0, 'x': 0, 'y': 0},
    32  : {'font_stroke': 1, 'font_size': 12, 'x': 0, 'y': 5},
    48  : {'font_stroke': 1, 'font_size': 14, 'x': 0, 'y': 6},
    64  : {'font_stroke': 1, 'font_size': 16, 'x': 0, 'y': 8},
    128 : {'font_stroke': 2, 'font_size': 30, 'x': 0, 'y': 16},
    256 : {'font_stroke': 4, 'font_size': 60, 'x': 0, 'y': 34},
    512 : {'font_stroke': 8, 'font_size': 120, 'x': 0, 'y': 68},
    1024: {'font_stroke': 16, 'font_size': 240, 'x': -3, 'y': 138},
  }

  def __draw_text_bottom_left(self, image, text):
    """
    Draws text on the image in the bottom-left corner.

    :type image: Image
    :param image: The image to modify.
    :type text: basestring
    :param text: The text to draw.
    """

    size = image.width
    if not text or size not in self.__TEXT_PARAMS or self.__TEXT_PARAMS[size]['font_size'] == 0:
      return
    params = self.__TEXT_PARAMS[size]
    x = -params['x']
    width = size
    height = size + params['y']
    with Image(width=width, height=height) as tmp:
      with Drawing() as draw:
        draw.gravity = 'south_east'
        draw.fill_color = Color('white')
        draw.stroke_color = Color('black') if params['font_stroke'] != 0 else Color('none')
        draw.stroke_width = params['font_stroke']
        draw.font = self.font
        draw.font_size = params['font_size']
        draw.text_kerning = 0.8
        draw.text(x, 0, text)
        draw.stroke_color = Color('none')
        draw.text(x, 0, text)
        draw(tmp)
      image.watermark(tmp)


def ensure_directory_exists(directory):
  if not os.path.exists(directory):
    os.makedirs(directory)

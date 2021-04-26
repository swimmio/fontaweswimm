#!/usr/local/bin/fontforge -script

import argparse
import json
import logging
import re
import typing
from pathlib import Path

INITIAL_UTF_GARBAGE_VALUE = 0xE900
IMPORT_OPTIONS = ('removeoverlap', 'correctdir')

DEFAULT_LANGUAGE = 'English (US)'
DEFAULT_FAMILY = None
DEFAULT_STYLE = 'Regular'

FONT_DIR_NAME = 'fonts'
DEMO_FILE_NAME = 'demo.html'
STYLE_FILE_NAME = 'style.css'
HTML_TEMPLATE_FILE = Path('html_template.html')
CSS_TEMPLATE_FILE = Path('css_template.css')

REGEX_NUMBER_OF_GLYPHS = r'{{ NUMBER_OF_GLYPHS }}'
REGEX_GLYPH_LIST = r'{{ GLYPH_LIST }}'
REGEX_STYLE_LIST = r'{{ STYLE_LIST }}'

config_type = typing.Dict[str, typing.Union[str, typing.List[str]]]
glyphs_type = typing.Dict[str]

logging.basicConfig(format='%(asctime)s %(levelname)s :: %(message)s', level=logging.DEBUG)
logger = logging.getLogger(__name__)

TEMPLATED_HTML = """
      <div class="glyph fs1">
        <div class="clearfix bshadow0 pbs">
          <span class="icon-{glyph_name}"></span>
          <span class="mls"> icon-{glyph_name}</span>
        </div>
        <fieldset class="fs0 size1of1 clearfix hidden-false">
          <input type="text" readonly value="{utf_code}" class="unit size1of2" />
          <input
            type="text"
            maxlength="1"
            readonly
            value="&#x{utf_code};"
            class="unitRight size1of2 talign-right"
          />
        </fieldset>
        <div class="fs0 bshadow0 clearfix hidden-true">
          <span class="unit pvs fgc1">liga: </span>
          <input type="text" readonly value="" class="liga unitRight" />
        </div>
      </div>
"""

TEMPLATED_CSS = """
.icon-{glyph_name}:before {{
  content: "\\\\{utf_code}";
}}
"""


def get_glyphs(icon_dir: Path) -> glyphs_type:
    """
    Generate a dict mapping a UTF code to it's relevant icon's path.

    :param icon_dir: directory of icons to turn into a font
    :type icon_dir: Path
    :return: utf code to icon path
    :rtype: typing.Dict[str, str]
    """
    glyphs = {}
    utf_counter = INITIAL_UTF_GARBAGE_VALUE
    for icon in sorted(icon_dir.iterdir()):
        utf_code = str(hex(utf_counter))
        icon_path = icon.absolute()
        glyphs[utf_code] = icon_path
        logging.debug(f'UTF:{utf_code} - {icon_path}')
        utf_counter += 1
    return glyphs


def load_config(base_conf_path: Path) -> config_type:
    """
    Get the base configuration which is the same with every font created.

    :param base_conf_path: path to the base config json
    :type base_conf_path: Path
    :return: dictionary consisting of the config object
    :rtype: typing.Dict[str, Union[str, typing.List[str]]]
    """
    return json.loads(base_conf_path.read_text())


def initialize_font(config: config_type, glyphs: glyphs_type) -> fontforge.font:
    """
    Create fontforge's "font" object and initialize it with the right configuration / glyphs.

    :param config: a loaded config (see `load_config`)
    :type config: config_type
    :param glyphs: mapping between utf-code to an icon path
    :type glyphs: glyphs_type
    :return: initialized font object, ready to be outputted
    :rtype: fontforge.font
    """
    base_font: fontforge.font = fontforge.font()
    logger.debug('set font')
    set_font_properties(base_font, config)
    logger.debug('add glyphs')
    add_font_glyphs(base_font, glyphs)
    return base_font


def set_font_properties(font: fontforge.font, config: config_type) -> None:
    """
    Apply properties from the config file to the font

    :param font: font object to be filled
    :type font: fontforge.font
    :param config: loaded config (see `load_config`)
    :type config: config_type
    """
    props: typing.Dict = config['props']
    lang: str = props.pop('lang', DEFAULT_LANGUAGE)
    family: str = props.pop('family', DEFAULT_FAMILY)
    style: str = props.pop('style', DEFAULT_STYLE)
    encoding: str = props.pop('encoding', 'UnicodeFull')
    font.encoding = encoding
    if family is not None:
        font.familyname = family
        font.fontname = family + '-' + style
        font.fullname = family + ' ' + style
    for key, value in config['props'].items():
        if hasattr(font, key):
            if isinstance(value, list):
                value = tuple(value)
            setattr(font, key, value)
        else:
            font.appendSFNTName(lang, key, value)
    for sfnt_name in config.get('sfnt_names', []):
        font.appendSFNTName(*sfnt_name)


def add_font_glyphs(font: fontforge.font, glyphs: glyphs_type) -> None:
    """
    Add the actual glyphs into the font

    :param font: font object to be filled
    :type font: fontforge.font
    :param config: loaded config (see `load_config`)
    :type config: config_type
    """
    for utf_code, icon_path in glyphs.items():
        logging.debug(f'{utf_code} ;; {icon_path}')
        char = font.createMappedChar(int(utf_code, base=0))
        char.importOutlines(str(icon_path), IMPORT_OPTIONS)
        char.removeOverlap()
        char.glyphname = Path(icon_path).stem


def parse_arguments() -> argparse.Namespace:
    """
    Parse arguments from the command line using argparse.

    :return: command line arguments
    :rtype: argparse.Namespace
    """
    parser = argparse.ArgumentParser(__file__)
    parser.add_argument('base_conf', type=Path, help='Path to the base config')
    parser.add_argument('icon_dir', type=Path, help='Path to the icons directory')
    parser.add_argument('template_dir', type=Path, help='Path to the templates directory')
    parser.add_argument(
        '-o', '--output_dir', type=Path, default=Path('output'), help='Path to resource output directory'
    )
    return parser.parse_args()


def generate_demo_html(output_dir: Path, template_dir: Path, glyphs: glyphs_type) -> None:
    """
    Create the `demo.html` file in the output directory.

    :param output_dir: where to store the generated file
    :type output_dir: Path
    :param template_dir: where the file's template is stored
    :type template_dir: Path
    :param glyphs: mapping between utf-code to an icon path
    :type glyphs: glyphs_type
    """
    raw_html = (template_dir / HTML_TEMPLATE_FILE).read_text()
    raw_html = re.sub(REGEX_NUMBER_OF_GLYPHS, str(len(glyphs)), raw_html)
    div_list = []
    for utf_code, icon_path in glyphs.items():
        utf_code = utf_code[len('0x') :]
        div_list.append(TEMPLATED_HTML.format(glyph_name=Path(icon_path).stem, utf_code=utf_code))
    raw_html = re.sub(REGEX_GLYPH_LIST, '\n'.join(div_list), raw_html)
    demo_path = output_dir / DEMO_FILE_NAME
    demo_path.write_text(raw_html)


def generate_style_css(output_dir: Path, template_dir: Path, glyphs: glyphs_type) -> None:
    """
    Create the `style.css` file in the output directory.

    :param output_dir: where to store the generated file
    :type output_dir: Path
    :param template_dir: where the file's template is stored
    :type template_dir: Path
    :param glyphs: mapping between utf-code to an icon path
    :type glyphs: glyphs_type
    """
    raw_css = (template_dir / CSS_TEMPLATE_FILE).read_text()
    classes_list = []
    for utf_code, icon_path in glyphs.items():
        utf_code = utf_code[len('0x') :]
        classes_list.append(TEMPLATED_CSS.format(glyph_name=Path(icon_path).stem, utf_code=utf_code))
    raw_css = re.sub(REGEX_STYLE_LIST, '\n'.join(classes_list), raw_css)
    style_path = output_dir / STYLE_FILE_NAME
    style_path.write_text(raw_css)


def main():
    args = parse_arguments()
    logging.info(f'Loading basic config from {args.base_conf}...')
    config = load_config(args.base_conf)
    logging.info(f'Loading glyphs from {args.icon_dir}...')
    glyphs = get_glyphs(args.icon_dir)
    logging.info('Initializing font object...')
    font = initialize_font(config, glyphs)
    logging.info('Generating output fonts...')
    font_dir = args.output_dir / FONT_DIR_NAME
    font_dir.mkdir(parents=True, exist_ok=True)
    for outfile in config['output_fonts']:
        outfile_path = font_dir / outfile
        logging.debug(f'Generating {outfile_path}')
        font.generate(str(outfile_path))
    logging.info('Generating html demo...')
    generate_demo_html(args.output_dir, args.template_dir, glyphs)
    logging.info('Generating css styles...')
    generate_style_css(args.output_dir, args.template_dir, glyphs)
    logging.info('Done!')


if __name__ == '__main__':
    main()

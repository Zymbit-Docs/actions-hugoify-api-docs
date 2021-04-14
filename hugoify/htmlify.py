import os, sys
from pathlib import Path
from lxml import etree
from lxml.builder import E

from copy import deepcopy

from pprint import pprint

from .utils import partial_dump, ugly_dump, verbose_dump, unserialize, _reserialize

from typing import Union, List
from contextlib import contextmanager
from collections.abc import MutableMapping
from .parser import DocPath, Node, TextNode

# if not sys.warnoptions:
#     import warnings

#     warnings.simplefilter("once")

import warnings

warnings.filterwarnings("once", category=RuntimeWarning)

PWD = (Path(__file__).resolve()).parent


class NotImplementedWarning(UserWarning):
    def __init__(self, message):
        self.mesage = message


def get_abs(relative):
    return str(PWD / relative)


def htmlify():
    input_dir = Path(os.environ["INPUT_RAWPATH"])
    output_dir = Path(os.environ["INPUT_OUTPUTPATH"])

    if not output_dir.exists():
        print("Exiting because there are no files to process...")
        sys.exit(0)

    # for f in output_dir.glob("python_docs.xml"):
    for f in ("python_docs.xml", "cpp_docs.xml"):
        f = output_dir / f

        renderer = Renderer(f, output_dir)


class Renderer:
    def __init__(self, input_file, output_dir):
        print(f"Processing {str(input_file)}...")

        # self.current_path = []

        self.input_file = input_file.resolve()

        self.rendered_file = output_dir / f"{self.input_file.stem}.md"
        self.rendered_lines = []

        tree = etree.parse(
            str(self.input_file),
            parser=etree.XMLParser(load_dtd=True, no_network=False, recover=True),
        )
        self.document_root = _reserialize(tree.getroot())

        self.parse_section(self.document_root.xpath("./section"))

        with self.rendered_file.open("w") as fp:
            for line, nl in self.rendered_lines:
                text = "".join((line, "\n" * nl))
                fp.write(text)

    def add_lines(self, line_or_lines: Union[str, List[str]], newlines: int = 2):
        if line_or_lines is None:
            pass
        elif type(line_or_lines) is TextNode:
            self.__add_line(line_or_lines.text, line_or_lines._newlines)
        elif type(line_or_lines) is list:
            self.__add_lines(line_or_lines, newlines)
        elif type(line_or_lines) is str:
            self.__add_line(line_or_lines, newlines)
        elif type(line_or_lines) is tuple:
            self.__add_line(line_or_lines)
        else:
            raise TypeError(
                f"Invalid type: {type(line_or_lines)}. Must past string or list of strings to this method."
            )

    def __add_line(self, line: str, newlines: int = 2):
        if type(line) is tuple:
            self.rendered_lines.append(line)
        elif type(line) is str:
            self.rendered_lines.append((line, newlines))
        else:
            raise TypeError(f"Invalid type passed to __add_line: {type(line)}.")
        # else:
        #     # self.rendered_lines.append((line.strip(), newlines))

    def __add_lines(self, lines: List[str], newlines: int = 2):
        for line in lines:
            self.__add_line(line, newlines)

    def parse_section(self, root):
        if type(root) is list:
            for elem in root:
                self.parse_section(elem)

            return

        section_id = root.get("id")
        if section_id == "abstract":
            section_title = "Introduction"
        elif section_id == "classes":
            section_title = "Classes"
        else:
            section_title = False
            return

        if section_title:
            self.add_lines(f"## {section_title}", newlines=2)

        with DocPath(f"section-{section_id}") as d:
            for child in root:
                # print("First child:", child)
                self.parse_node(child, context=d)

    def get_node(self, node, newlines: int = None, subfunction: str = None, **kwargs):
        # kwargs = deepcopy(kwargs)
        tag = node.tag

        # if tag == "desc":
        #     kwargs["objtype"] = node.get("objtype")

        if subfunction is not None:
            tag = f"{tag}_{subfunction}"

        kwargs["parsing_trigger"] = kwargs.get("parsing_trigger", "get_node")

        if node.tail and not node.tail.isspace():
            warnings.warn(
                (
                    f"The element {tag} contains a tail. No elements should have tails.\n"
                    f"\tBase: {node.base}\n"
                    f"\tLine: {node.sourceline}\n"
                    f"\tTail text:\n\t\t{node.tail}"
                ),
                category=RuntimeWarning,
            )

        func_name = f"_parse_node_{tag}"
        parse_func = self.__get_parse_func(func_name)
        if newlines is None:
            lines = parse_func(node, **kwargs)
        else:
            lines = parse_func(node, newlines=newlines, **kwargs)

        if lines is not None:
            return lines
        else:
            return None

    def parse_node(self, node, newlines: int = None, **kwargs):
        kwargs["parsing_trigger"] = kwargs.get("parsing_trigger", "get_node")
        self.add_lines(self.get_node(node, newlines, **kwargs))

    def parse_content(self, node, **kwargs):
        # print(f"{node}: ", end="")
        # print("Parsing:", node)
        if len(node) == 0:
            if node.text:
                new_node = TextNode(node.text)
            else:
                new_node = TextNode("")
        else:
            node_text = ""
            node_tail = ""
            new_node = []
            if node.text:
                node_text = node.text

            for sub_item in node:
                tag = sub_item.tag
                func_name = f"_parse_content_{tag}"
                parse_func = self.__get_parse_func(func_name)

                new_node.append(parse_func(sub_item, **kwargs))

            if node.tail:
                node_tail = node.tail.strip()

        return new_node

    def __get_parse_func(self, func_name):
        parse_func = getattr(self, func_name, None)

        if parse_func is not None:
            return parse_func

        warnings.warn(NotImplementedWarning(f"{func_name}"))

        if func_name.startswith("_parse_content_"):
            return lambda *args, **kwargs: ""
        else:
            return lambda *args, **kwargs: None

    def __not_implemented_warning(self, node, **kwargs):
        print(f"A parsing method has not been implemented for the {node.tag} element.")

    def __serialize_html(self, node, **kwargs):
        new_tree = deepcopy(node)
        serialized = etree.tostring(new_tree, encoding="utf-8").decode("utf-8")

        return serialized

    def make_header(self, node, **kwargs):
        heading_level = kwargs.get("heading_level", 2)

        marks = "#" * heading_level
        return TextNode(f"{marks} {node}", newlines=2)

    def _parse_node_paragraph(self, node, newlines: int = 2, **kwargs):
        return TextNode(self.parse_content(node), newlines=2)

    def _parse_node_enumerated_list(self, node, **kwargs):
        new_lines = []
        for item in node:
            # print("Parsing content:", item)
            item_content = self.get_node(item)
            # print("Item content:", item_content)
            line = f"1. {item_content}"

            new_lines.append((line, 1))

        # self.add_lines("", newlines=1)
        new_lines.append(("", 1))

        return new_lines

    def _parse_node_list_item(self, node, **kwargs):
        return TextNode(self.parse_content(node, **kwargs), newlines=1)

    def _parse_node_desc(self, node, **kwargs):
        objtype = node.get("objtype", "NO_OBJ_TYPE")
        self.parse_node(node, subfunction=objtype, **kwargs)

    def _parse_node_desc_class(self, node, **kwargs):
        with DocPath(f"class", increment_heading=True, **kwargs) as d:
            for child in node:
                self.parse_node(child, **d)

    def _parse_node_desc_function(self, node, **kwargs):
        self._parse_node_desc_method(node, **kwargs)

    def _parse_node_desc_method(self, node, **kwargs):
        with DocPath(f"function", increment_heading=True, **kwargs) as d:
            for child in node:
                self.parse_node(child, **d)

    def _parse_node_desc_signature(self, node, **kwargs):

        with DocPath(f"signature", **kwargs) as d:
            node_wrapper = Node("span", classes=d.classes)

            for item in node:
                parsed_item = self.get_node(item, **d)
                if parsed_item is not None:
                    node_wrapper.append(parsed_item)

            return TextNode(self.make_header(node_wrapper, **d), newlines=2)

    def _parse_node_desc_returns(self, node, **kwargs):
        with DocPath("return-type", **kwargs) as d:
            node_wrapper = Node("span", classes="return-type", render_empty=False)
            node_wrapper.text = self.parse_content(node)
            node_wrapper.tail = " "

        return node_wrapper

    def _parse_node_desc_ref(self, node, **kwargs):
        with DocPath("pointer-ref", **kwargs) as d:
            node_wrapper = Node("span", classes="pointer-ref", render_empty=False)
            node_wrapper.text = self.parse_content(node)

        return node_wrapper

    def _parse_node_desc_annotation(self, node, **kwargs):
        with DocPath("annotation", **kwargs) as d:
            node_wrapper = Node("span", classes="annotation")
            node_wrapper.text = self.parse_content(node)
            node_wrapper.tail = " "

        return node_wrapper

    def _parse_node_desc_addname(self, node, **kwargs):
        with DocPath("addname", **kwargs) as d:
            node_wrapper = Node("span", classes="addname")
            node_wrapper.text = self.parse_content(node)

        return node_wrapper

    def _parse_node_desc_name(self, node, **kwargs):
        with DocPath("addname", **kwargs) as d:
            node_wrapper = Node("span", classes="name")
            node_wrapper.text = self.parse_content(node)

        return node_wrapper

    def _parse_node_desc_content(self, node, **kwargs):
        for elem in node:
            self.parse_node(elem, **kwargs)

    def _parse_node_desc_parameterlist(self, node, **kwargs):
        with DocPath("parameter-list", **kwargs) as d:
            node_wrapper = Node("span", classes="parameter-list")
            # node_wrapper.text = "("
            # node_wrapper.text = self.parse_content(node)
            node_wrapper.append(TextNode("("))
            for item in node:
                parsed_item = self.get_node(item, **d)
                if parsed_item is not None:
                    node_wrapper.append(parsed_item)
            node_wrapper.append(TextNode(")"))

        return node_wrapper

    def _parse_node_desc_parameter(self, node, **kwargs):
        with DocPath("parameter", **kwargs) as d:
            node_wrapper = Node("span", classes="param")

            for item in node:
                parsed_item = self.get_node(item, **d)
                if parsed_item is not None:
                    node_wrapper.append(parsed_item)
                    node_wrapper.append(TextNode(","), not_last=True)

            return node_wrapper

    #     node_wrapper = Node("span", classes="param")
    #     node_wrapper.text = self.parse_content(node)

    # return node_wrapper

    def _parse_content_paragraph(self, node, **kwargs):
        return TextNode(self.parse_content(node, **kwargs), newlines=1)

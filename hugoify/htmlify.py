import os, sys
from pathlib import Path
from html import unescape
from lxml import etree
from lxml import html
from lxml.builder import E

from copy import deepcopy

from pprint import pprint

from .utils import partial_dump, ugly_dump, verbose_dump, unserialize, _reserialize

from typing import Union, List
from contextlib import contextmanager
from collections.abc import MutableMapping
from .parser_utils import DocTree, Node

from re import sub as re_sub

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
        # self.rendered_lines = []
        self.rendered_trees = []

        tree = etree.parse(
            str(self.input_file),
            parser=etree.XMLParser(load_dtd=True, no_network=False, recover=True),
        )
        self.document_root = _reserialize(tree.getroot())

        frontmatter = etree.XSLT(etree.parse(get_abs("xslt/frontmatter.xslt")))
        generated_frontmatter = str(frontmatter(tree.getroot())).lstrip()

        self.parse_section(self.document_root.xpath("./section"))

        with self.rendered_file.open("w") as fp:
            fp.write(generated_frontmatter)
            for block in self.rendered_trees:
                raw = block.raw()
                etree.indent(raw, space="    ", level=0)
                text = etree.tostring(raw).decode("utf-8")

                text = self.tidy_text(text)
                fp.write(text)
                fp.write("\n")

    def tidy_text(self, text):

        text = re_sub(
            r"&#8221;([\w -]+?)&#8221;",
            r"&#8220;\1&#8221;",
            text,
        )

        text = re_sub(
            r"&#8216;([\w -]+?)&#8217;",
            r"&#8220;\1&#8221;",
            text,
        )

        text = re_sub(
            r"<span class=\"default-val\">'([\w -]+?)'</span>",
            r'<span class="default-val">"\1"</span>',
            text,
        )

        return text

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

        with DocTree("div", opening_newline=True) as d:
            node = Node("div", **d)
            # d.add_hang(node)

            with DocTree("h", **d) as d_h:
                title_node = Node("h", section_title, **d_h)
                node.append(title_node)

                # with DocTree(None, increment_heading=True, **d) as d_contents:
                for child in root:
                    self.parse_tree(node, child, context=d_h)

                self.rendered_trees.append(node)

    def extract_tree(self, node, subfunction: str = None, context=None, **kwargs):
        tag = node.tag

        if subfunction is not None:
            tag = f"{tag}_{subfunction}"

        if node.tail and not node.tail.isspace():
            if node.tag not in {"strong", "title_reference"}:
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
        children = parse_func(node, context=context, **kwargs)

        return children

    def parse_tree(self, parent, node, subfunction: str = None, context=None, **kwargs):
        children = self.extract_tree(node, subfunction, context=context, **kwargs)

        if children is None:
            return None
        elif type(children) is list:
            parent.extend(children)
        else:
            parent.append(children)

    def __get_parse_func(self, func_name):
        parse_func = getattr(self, func_name, None)

        if parse_func is not None:
            return parse_func

        warnings.warn(NotImplementedWarning(f"{func_name}"))

        if func_name.startswith("_parse_content_"):
            return lambda *args, **kwargs: ""
        else:
            return lambda *args, **kwargs: None

    def _parse_node_strong(self, node, context=None, **kwargs):
        with DocTree("strong", **context) as d:
            elem = Node("strong", **d)
            parsed = self.parse_content(elem, node, context=d, **kwargs)
            return parsed

    def _parse_node_title_reference(self, node, context=None, **kwargs):
        with DocTree("span", **context) as d:
            elem = Node("span", classes="title-reference", **d)
            parsed = self.parse_content(elem, node, context=d, **kwargs)
            return parsed

    def _parse_node_paragraph(self, node, context=None, **kwargs):
        with DocTree("p", **context) as d:
            elem = Node("p", **d)  # E.p()
            parsed = self.parse_content(elem, node, context=d, **kwargs)
            return parsed

    def _parse_node_enumerated_list(self, node, context=None, **kwargs):
        with DocTree("ol", **context) as d:
            elem = Node("ol", **d)  # E.ol()
            parsed = self.parse_content(elem, node, context=d, **kwargs)
            # indented = parsed.indent()
            return parsed

    def _parse_node_bullet_list(self, node, context=None, **kwargs):
        with DocTree("ul", **context) as d:
            elem = Node("ul", **d)  # E.ol()
            parsed = self.parse_content(elem, node, context=d, **kwargs)
            # indented = parsed.indent()
            return parsed

    def _parse_node_list_item(self, node, context=None, **kwargs):
        with DocTree("li", **context) as d:
            elem = Node("li", **d)  # E.li()
            elem = self.parse_content(elem, node, context=d, **kwargs)
            # print(type(elem))
            # print(elem.tag)
            return self.unnest_content(elem, **kwargs)

    def _parse_node_desc(self, node, context=None, **kwargs):
        objtype = node.get("objtype", "NO_OBJ_TYPE")
        return self.extract_tree(node, subfunction=objtype, context=context, **kwargs)

    def _parse_node_definition_list(self, node, context=None, **kwargs):
        objtype = node.get("content-type", "NO_OBJ_TYPE")
        return self.extract_tree(node, subfunction=objtype, context=context, **kwargs)

    def _parse_node_desc_class(self, node, context=None, **kwargs):
        with DocTree("div", **context) as d:
            elem = Node("div", **d)  # E.div()
            elem.set("class", "class")

            for child in node:
                if (
                    extracted := self.extract_tree(child, context=d, **kwargs)
                ) is not None:
                    elem.append(extracted)

            return elem

    def _parse_node_desc_signature(self, node, context=None, **kwargs):
        with DocTree(
            "h", indent_children=False, increment_heading=True, **context
        ) as d:
            node_wrapper = Node("h", **d)  # E.span()
            node_wrapper.set("class", "signature")

            for item in node:
                if (
                    extracted := self.extract_tree(item, context=d, **kwargs)
                ) is not None:
                    node_wrapper.append(extracted)

        return node_wrapper

    def _parse_node_desc_annotation(self, node, context=None, **kwargs):
        node_wrapper = Node("span")  # E.span()
        node_wrapper.set("class", "annotation")

        node_wrapper = self.parse_content(node_wrapper, node, context=context, **kwargs)
        node_wrapper.tail += " "
        return node_wrapper

    def _parse_node_desc_addname(self, node, context=None, **kwargs):
        node_wrapper = Node("span")  # E.span()
        node_wrapper.set("class", "addname")

        return self.parse_content(node_wrapper, node, context=context, **kwargs)

    def _parse_node_desc_name(self, node, context=None, **kwargs):
        node_wrapper = Node("span")  # E.span()
        node_wrapper.set("class", "name")

        return self.parse_content(node_wrapper, node, context=context, **kwargs)

    def _parse_node_default_value(self, node, context=None, **kwargs):
        node_wrapper = Node("span")  # E.span()
        node_wrapper.set("class", "default-val")

        return self.parse_content(node_wrapper, node, context=context, **kwargs)

    def _parse_node_desc_content(self, node, context=None, **kwargs):
        with DocTree("div", increment_heading=True, **context) as d:
            elem = Node("div", **d)
            elem.set("class", "body")
            return self.parse_content(elem, node, context=d, **kwargs)
        # all_elems = []
        # with DocTree("div", **context) as d:
        #     description_wrapper = Node("div", **d)  # E.span()
        #     description_wrapper.set("class", "description")

        #     for item in node.xpath("./desc/preceding-sibling::paragraph"):
        #         with DocTree("p", **d) as d_p:
        #             p_node = Node("p", **d_p)
        #             description_wrapper.append(
        #                 self.parse_content(p_node, item, context=d_p, **kwargs)
        #             )

        #     all_elems.append(description_wrapper)

        # with DocTree("div", **context) as d:
        #     methods_wrapper = Node("div", **d)
        #     methods_wrapper.set("class", "body")

        #     for item in node.xpath("./*[not(name()='paragraph')]"):
        #         all_elems.append(
        #             self.parse_content(methods_wrapper, item, context=d, **kwargs)
        #         )
        # with DocTree("")

        # with DocTree("div", **context) as d:

        # if (
        #     extracted := self.extract_tree(item, context=d, **kwargs)
        # ) is not None:
        #     node_wrapper.append(extracted)

        # return all_elems

    def _parse_node_desc_function(self, node, context=None, **kwargs):
        return self._parse_node_desc_method(node, context=context, **kwargs)

    def _parse_node_desc_method(self, node, context=None, **kwargs):
        with DocTree("div", increase_heading=True, **context) as d:
            elem = Node("div", **d)  # E.div()
            elem.set("class", "method")

            for child in node:
                if (
                    extracted := self.extract_tree(child, context=d, **kwargs)
                ) is not None:
                    elem.append(extracted)

            return elem

    def _parse_node_desc_attribute(self, node, context=None, **kwargs):
        with DocTree("div", increase_heading=True, **context) as d:
            elem = Node("div", **d)  # E.div()
            elem.set("class", "attribute")

            for child in node:
                if (
                    extracted := self.extract_tree(child, context=d, **kwargs)
                ) is not None:
                    elem.append(extracted)

            return elem

    def _parse_node_desc_returns(self, node, context=None, **kwargs):
        with DocTree("span", **context) as d:
            node_wrapper = Node("span", **d)  # E.span()
            node_wrapper.set("class", "returns")

            return self.parse_content(node_wrapper, node, context=context, **kwargs)

    def _parse_node_desc_ref(self, node, context=None, **kwargs):
        with DocTree("span", **context) as d:
            node_wrapper = Node("span", **d)  # E.span()
            node_wrapper.set("class", "pointer-ref")

            return self.parse_content(node_wrapper, node, context=context, **kwargs)

    def _parse_node_desc_parameterlist(self, node, context=None, **kwargs):
        with DocTree("span", **context) as d:
            node_wrapper = Node("span", **d)  # E.span()
            node_wrapper.set("class", "param-list")
            node_wrapper.text += "("

            parsed = self.parse_content(node_wrapper, node, context=context, **kwargs)
            # parsed._content[-1].tail += ")"
            return parsed

    def _parse_node_desc_parameter(self, node, context=None, **kwargs):
        with DocTree("span", **context) as d:
            node_wrapper = Node("span", **d)  # E.span()
            node_wrapper.set("class", "param")

            parsed = self.parse_content(node_wrapper, node, context=context, **kwargs)
            return parsed

    def _parse_node_desc_type(self, node, context=None, **kwargs):
        with DocTree("span", **context) as d:
            node_wrapper = Node("span", **d)  # E.span()
            node_wrapper.set("class", "type")

            parsed = self.parse_content(node_wrapper, node, context=context, **kwargs)
            return parsed

    def _parse_node_func_description(self, node, context=None, **kwargs):
        with DocTree("div", **context) as d:
            elem = Node("div", **d)  # E.ol()
            elem.set("class", "description")
            parsed = self.parse_content(elem, node, context=d, **kwargs)
            # indented = parsed.indent()
            return parsed

    def _parse_node_definition_list_parameters(self, node, context=None, **kwargs):
        with DocTree("div", **context) as d:
            node_wrapper = Node("div", **d)  # E.span()
            node_wrapper.set("class", "parameters")

            with DocTree("h", increment_heading=True, **d) as d_h:
                node_wrapper.append(Node("h", "Parameters", **d_h))

            with DocTree("ul", **d) as d_ol:
                ol = Node("ul", **d_ol)
                parsed = self.parse_content(ol, node, context=d_ol, **kwargs)
                node_wrapper.append(parsed)
                # parsed._content[-1].tail += ")"

        return node_wrapper

    def _parse_node_param(self, node, context=None, **kwargs):
        with DocTree("li", **context) as d:
            node_wrapper = Node("li", **d)  # E.span()
            node_wrapper.set("class", "param-item")

            for item in node:
                if (
                    extracted := self.extract_tree(item, context=d, **kwargs)
                ) is not None:
                    node_wrapper.append(extracted)

        return node_wrapper

    def _parse_node_param_name(self, node, context=None, **kwargs):
        node_wrapper = Node("span")  # E.span()
        node_wrapper.set("class", "name")

        return self.parse_content(node_wrapper, node, context=context, **kwargs)

    def _parse_node_param_type(self, node, context=None, **kwargs):
        node_wrapper = Node("span")  # E.span()
        node_wrapper.set("class", "type")

        return self.parse_content(node_wrapper, node, context=context, **kwargs)

    def _parse_node_param_desc(self, node, context=None, **kwargs):
        node_wrapper = Node("span")  # E.span()
        node_wrapper.set("class", "description")

        return self.parse_content(node_wrapper, node, context=context, **kwargs)

    def _parse_node_source_file(self, node, context=None, **kwargs):
        node_wrapper = Node("span")  # E.span()
        node_wrapper.set("class", "source-file")

        return self.parse_content(node_wrapper, node, context=context, **kwargs)

    def _parse_node_definition_list_exceptions(self, node, context=None, **kwargs):
        with DocTree("div", **context) as d:
            node_wrapper = Node("div", **d)  # E.span()
            node_wrapper.set("class", "exceptions")

            with DocTree("h", increment_heading=True, **d) as d_h:
                node_wrapper.append(Node("h", "Exceptions", **d_h))

            with DocTree("ul", **d) as d_ol:
                ol = Node("ul", **d_ol)
                parsed = self.parse_content(ol, node, context=d_ol, **kwargs)
                node_wrapper.append(parsed)
                # parsed._content[-1].tail += ")"

        return node_wrapper

    def _parse_node_exception(self, node, context=None, **kwargs):
        with DocTree("li", **context) as d:
            node_wrapper = Node("li", **d)  # E.span()
            node_wrapper.set("class", "exc-item")

            for item in node:
                if (
                    extracted := self.extract_tree(item, context=d, **kwargs)
                ) is not None:
                    node_wrapper.append(extracted)

        return node_wrapper

    def _parse_node_exception_name(self, node, context=None, **kwargs):
        node_wrapper = Node("span")  # E.span()
        node_wrapper.set("class", "name")

        return self.parse_content(node_wrapper, node, context=context, **kwargs)

    def _parse_node_exception_desc(self, node, context=None, **kwargs):
        node_wrapper = Node("span")  # E.span()
        node_wrapper.set("class", "description")

        return self.parse_content(node_wrapper, node, context=context, **kwargs)

    # def serialize_children(self, node, **kwargs):
    #     serialized_children = []

    #     for child in node:
    #         # serialized = etree.fromstring(etree.tostring(child, encoding="unicode"))
    #         serialized = etree.tostring(child.raw, encoding="unicode")
    #         # serialized = s
    #         serialized_children.append(serialized)
    #         node.remove(child)

    #     # print(etree.tostringlist(serialized_children, encoding="unicode"))
    #     return "".join(serialized_children)
    #     # return serialized_children

    def parse_content(self, parent, node, context=None, **kwargs):
        parent.text = ""
        parent.tail = ""

        if node.text:
            parent.add_text(node.text)

        for child in node:
            self.parse_tree(parent, child, context=context)

        if node.tail:
            parent.tail = node.tail.rstrip()
            parent.tail += " "

        return parent

    def __not_implemented_warning(self, node, **kwargs):
        print(f"A parsing method has not been implemented for the {node.tag} element.")

    def unnest_content(self, elem, context=None, **kwargs):
        new_elem = Node(elem.tag)  # E(elem.tag)

        for key, val in elem.items():
            new_elem.set(key, val)

        UNNESTABLE = set(
            "p",
        )
        if len(elem) == 1:
            child = next(iter(elem))

            if child.tag not in UNNESTABLE:
                new_elem.append(child)
            else:
                if child.text:
                    new_elem.text = child.text

                for nested_child in child:
                    new_elem.append(self.unnest_content(nested_child))

                if child.tail:
                    new_elem.tail = child.tail

            return new_elem
        else:
            return elem

    # def __serialize_html(self, node, **kwargs):
    #     new_tree = deepcopy(node)
    #     serialized = etree.tostring(new_tree, encoding="utf-8").decode("utf-8")

    #     return serialized

    # def make_header(self, node, **kwargs):
    #     heading_level = kwargs.get("heading_level", 2)

    #     marks = "#" * heading_level
    #     return TextNode(f"{marks} {node}", newlines=2)

    # def _parse_node_enumerated_list(self, node, **kwargs):
    #     new_lines = []
    #     for item in node:
    #         # print("Parsing content:", item)
    #         item_content = self.get_node(item)
    #         # print("Item content:", item_content)
    #         line = f"1. {item_content}"

    #         new_lines.append((line, 1))

    #     # self.add_lines("", newlines=1)
    #     new_lines.append(("", 1))

    #     return new_lines

    # def _parse_node_list_item(self, node, **kwargs):
    #     return TextNode(self.parse_content(node, **kwargs), newlines=1)

    # def _parse_node_desc_function(self, node, **kwargs):
    #     self._parse_node_desc_method(node, **kwargs)

    # def _parse_node_desc_method(self, node, **kwargs):
    #     with DocPath(f"function", increment_heading=True, **kwargs) as d:
    #         for child in node:
    #             self.parse_node(child, **d)

    # def _parse_node_desc_signature(self, node, **kwargs):

    #     with DocPath(f"signature", **kwargs) as d:
    #         node_wrapper = Node("span", classes=d.classes)

    #         for item in node:
    #             parsed_item = self.get_node(item, **d)
    #             if parsed_item is not None:
    #                 node_wrapper.append(parsed_item)

    #         return TextNode(self.make_header(node_wrapper, **d), newlines=2)

    # def _parse_node_desc_returns(self, node, **kwargs):
    #     with DocPath("return-type", **kwargs) as d:
    #         node_wrapper = Node("span", classes="return-type", render_empty=False)
    #         node_wrapper.text = self.parse_content(node)
    #         node_wrapper.tail = " "

    #     return node_wrapper

    # def _parse_node_desc_ref(self, node, **kwargs):
    #     with DocPath("pointer-ref", **kwargs) as d:
    #         node_wrapper = Node("span", classes="pointer-ref", render_empty=False)
    #         node_wrapper.text = self.parse_content(node)

    #     return node_wrapper

    # def _parse_node_desc_annotation(self, node, **kwargs):
    #     with DocPath("annotation", **kwargs) as d:
    #         node_wrapper = Node("span", classes="annotation")
    #         node_wrapper.text = self.parse_content(node)
    #         node_wrapper.tail = " "

    #     return node_wrapper

    # def _parse_node_desc_addname(self, node, **kwargs):
    #     with DocPath("addname", **kwargs) as d:
    #         node_wrapper = Node("span", classes="addname")
    #         node_wrapper.text = self.parse_content(node)

    #     return node_wrapper

    # def _parse_node_desc_name(self, node, **kwargs):
    #     with DocPath("addname", **kwargs) as d:
    #         node_wrapper = Node("span", classes="name")
    #         node_wrapper.text = self.parse_content(node)

    #     return node_wrapper

    # def _parse_node_desc_content(self, node, **kwargs):
    #     for elem in node:
    #         self.parse_node(elem, **kwargs)

    # def _parse_node_desc_parameterlist(self, node, **kwargs):
    #     with DocPath("parameter-list", **kwargs) as d:
    #         node_wrapper = Node("span", classes="parameter-list")
    #         # node_wrapper.text = "("
    #         # node_wrapper.text = self.parse_content(node)
    #         node_wrapper.append(TextNode("("))
    #         for item in node:
    #             parsed_item = self.get_node(item, **d)
    #             if parsed_item is not None:
    #                 node_wrapper.append(parsed_item)
    #         node_wrapper.append(TextNode(")"))

    #     return node_wrapper

    # def _parse_node_desc_parameter(self, node, **kwargs):
    #     with DocPath("parameter", **kwargs) as d:
    #         node_wrapper = Node("span", classes="param")

    #         for item in node:
    #             parsed_item = self.get_node(item, **d)
    #             if parsed_item is not None:
    #                 node_wrapper.append(parsed_item)
    #                 node_wrapper.append(TextNode(","), not_last=True)

    #         return node_wrapper

    #     node_wrapper = Node("span", classes="param")
    #     node_wrapper.text = self.parse_content(node)

    # return node_wrapper

    # def _parse_content_paragraph(self, node, **kwargs):
    #     return TextNode(self.parse_content(node, **kwargs), newlines=1)

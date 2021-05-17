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

import re
from re import sub as re_sub

from hashlib import md5

from itertools import chain
import warnings

warnings.filterwarnings("once", category=RuntimeWarning)

PWD = (Path(__file__).resolve()).parent


class NotImplementedWarning(UserWarning):
    def __init__(self, message):
        self.mesage = message


def get_abs(relative):
    return str(PWD / relative)


def htmlify(input_dir, output_dir):
    if not input_dir:
        input_dir = Path(os.environ["INPUT_RAWPATH"])
    if not output_dir:
        output_dir = Path(os.environ["INPUT_OUTPUTPATH"])

    if not input_dir.exists():
        print("Exiting because there are no files to process...")
        sys.exit(0)

    # for f in output_dir.glob("python_docs.xml"):
    for f in input_dir.glob("*-processed.xml"):  # ("python_docs.xml", "cpp_docs.xml"):
        # f = output_dir / f

        renderer = Renderer(f, output_dir)


class Renderer:
    def __init__(self, input_file, output_dir):
        print(f"Processing {str(input_file)}...")

        # self.current_path = []

        self.input_file = input_file.resolve()

        output_filename = self.input_file.stem.replace("-processed", "")
        output_filename = output_filename.replace("GENERATED_", "")

        self.rendered_file = output_dir / f"{output_filename}.md"
        # self.rendered_lines = []
        self.rendered_trees = []

        tree = etree.parse(
            str(self.input_file),
            parser=etree.XMLParser(load_dtd=True, no_network=False, recover=True),
        )
        self.document_root = _reserialize(tree.getroot())

        frontmatter = etree.XSLT(etree.parse(get_abs("xslt/frontmatter.xslt")))
        generated_frontmatter = str(frontmatter(tree.getroot())).lstrip()

        self.toc = {}

        self.parse_section(self.document_root.xpath("./section"))

        with self.rendered_file.open("w") as fp:
            fp.write(generated_frontmatter)
            for block in self.rendered_trees:

                raw = block.raw()

                for elem in raw.xpath(".//span[@class='pointer-ref']"):
                    elem.tail = elem.tail.strip()

                for child in raw.getchildren():
                    dumped = etree.tostring(
                        child, encoding="unicode", pretty_print=True
                    )
                    reparsed = etree.fromstring(
                        dumped, parser=etree.XMLParser(recover=True)
                    )

                    for subchild in reparsed.getchildren():
                        etree.indent(subchild, space="  ", level=0)

                    raw.replace(child, reparsed)

                etree.indent(raw, space="", level=0)

                for header in raw.xpath(".//*[contains(@class, 'include-toc')]"):
                    header.tail = f"\n{header.tail}"

                    parent = header.getparent()
                    if parent.index(header) == 0:
                        parent.text = f"\n{parent.text}"

                    self.strip_newlines(header)

                    heading_level = header.tag.replace("h", "")
                    children_line = deepcopy(header.getchildren())

                    heading_line = E.span()
                    heading_line.text = header.text.strip()
                    heading_line.set(
                        "class",
                        " ".join([f"markdown-h{heading_level}", header.get("class")]),
                    )
                    heading_line.extend(children_line)

                    self.reparse_heading_line(heading_line)
                    self.generate_heading_id(heading_line)

                    header.addnext(heading_line)
                    header.getparent().replace(
                        header, E(f"heading_level_{heading_level}")
                    )

                text = etree.tostring(
                    raw,
                    # pretty_print=True,
                ).decode("utf-8")

                text = self.tidy_text(text)
                text = self.replace_headers(text)
                fp.write(text)
                fp.write("\n")

                # etree.indent(raw, space="  ")

    def reparse_heading_line(self, line):
        """Add display elements to heading line.

        The XML that is fed to this class doesn't have structural elements necessary
        for HTML display, such as parentheses around the parameter list of a
        method or commas between each parameter. This method adds those elements
        to the header lines.
        """
        param_list = line.xpath("./span[contains(@class, 'param-list')]")

        if len(param_list):
            param_list = param_list[0]
        else:
            return

        opener_elem = E.span("( ")
        opener_elem.set("class", "param-paren paren-open")
        param_list.insert(0, opener_elem)

        closer_elem = E.span(" )")
        closer_elem.set("class", "param-paren paren-close")
        param_list.append(closer_elem)

        for elem in line.iter(tag="span"):
            if elem.text is not None:
                elem.text = elem.text.replace("_", "\_")

        for param in param_list.xpath("./span[@class='param']")[:-1]:
            old_tail = ""
            if param.tail is not None:
                old_tail = param.tail

            param.tail = f", {old_tail}"

        for elem in param_list.xpath(".//span[@class='default-val']"):
            prev_elem = elem.getprevious()
            prev_elem.tail = " = "

            if elem.text.startswith("- "):
                elem.text = elem.text.replace("- ", "-")

    def replace_headers(self, text):

        header_string = r"<heading_level_(?P<heading_level>\d)/>"
        matches = re.finditer(header_string, text)

        new_text = []
        last_match_end = 0
        for match in matches:
            new_text.append(text[last_match_end : match.start()])
            last_match_end = match.end()

            match_dict = match.groupdict()
            new_header = f'{"#" * int(match_dict["heading_level"])} '

            new_text.append(new_header)

        new_text.append(text[last_match_end:])
        return "".join(new_text)

    def generate_heading_id(self, line):
        """Add a heading ID to each header.

        For permalinks to sections and within the table of contents, Hugo will
        automatically generate an ID for the anchor link. Because the full content
        of the line can be very long for methods with many parameters, we can
        generate our own simplified heading ID to append to each line, which
        Hugo will then use.
        """

        # Get the non-parameter elements of the function signature. This can
        # include the return type, as well as the function's name.
        name_elems = line.xpath("./span[not(contains(@class, 'param-list'))]")
        id_string = []
        for elem in name_elems:
            if elem.text is not None:

                # We can simplify the link names by removing any spaces or underscores
                # from the individual components of the function signature.
                id_elem = elem.text.strip()
                id_elem = id_elem.replace(" ", "")
                id_elem = id_elem.replace("_", "")
                id_elem = id_elem.replace("\\", "")
                id_string.append(id_elem)

        # Join the primary components of the heading ID (e.g. return type and name)
        # with underscores.
        heading_id = "_".join(id_string)

        # Get the list of parameter elements defined in this function/method
        # signature. We will need to use these to differentiate between
        # overloaded functions that share a name and return type.
        param_list = line.xpath("./span[contains(@class, 'param-list')]")

        if len(param_list):
            param_list = param_list[0]
        else:
            return
        param_str_elems = param_list

        # We are taking the first four characters from each sub-element in the parameter
        # list (e.g. the first four characters of an argument type, name, etc.),
        # combining those fragments with underscores, and hashing the result. Then,
        # we append the first eight characters of the resulting hash to the heading ID.
        #
        # This is done because the full parameter list can be quite long, but the first
        # four characters of each elem combined and hashed results in a string that
        # will be unique for that particular set of parameters.
        param_str = "_".join(
            [_.strip()[:4] for _ in param_list.itertext() if len(_.strip())]
        )
        param_str = md5(param_str.encode("utf-8")).hexdigest()[:8]
        heading_id = "_".join(id_string + [param_str])
        heading_id = heading_id.replace("*_", "")

        old_tail = ""
        if line.tail is not None:
            old_tail = line.tail

        classes = line.get("class")
        del line.attrib["class"]

        line.tail = f' {{id="{heading_id}" class="{classes}"}}{old_tail}'

    def strip_newlines(self, elem):
        elem.text = elem.text.strip()
        for subchild in elem.getchildren():
            subchild.tail = subchild.tail.strip()

            if len(subchild.getchildren()):
                self.strip_newlines(subchild)

    # def stringify(self, raw):
    #     parts = (
    #         [raw.text]
    #         + list(
    #             chain(
    #                 *(
    #                     [c.text, etree.tostring(c).decode("utf-8"), c.tail]
    #                     for c in raw.getchildren()
    #                 )
    #             )
    #         )
    #         + [raw.tail]
    #     )
    #     # filter removes possible Nones in texts and tails
    #     return "".join(filter(None, parts))

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
        elif section_id == "functions":
            section_title = "Functions"
        elif section_id == "typedefs":
            section_title = "Typedefs"
        elif section_id == "enums":
            section_title = "Enums"
        elif section_id == "structs":
            section_title = "Structs"
        else:
            section_title = False
            return

        with DocTree("div", opening_newline=True) as d:
            node = Node("div", **d)
            node.set("class", "api-docs")

            with DocTree("h", **d) as d_h:
                title_node = Node("h", section_title, **d_h)
                title_node.set("class", "include-toc")
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
            if node.tag not in {"strong", "title_reference", "emphasis"}:
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

    def _parse_node_emphasis(self, node, context=None, **kwargs):
        with DocTree("em", **context) as d:
            elem = Node("em", **d)
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

    def _parse_node_return_value(self, node, context=None, **kwargs):
        with DocTree("div", **context) as d:
            wrapper = Node("div", **d)
            wrapper.set("class", "returns")

            with DocTree("h", **d) as d_h:
                wrapper.append(Node("h", "Returns", **d_h))

            return_type_elem_orig = node.getparent().find("return_type")
            if return_type_elem_orig is not None:
                return_type_elem = deepcopy(return_type_elem_orig)
                return_type_elem_orig.getparent().remove(return_type_elem_orig)

                type_elem = Node("span", **d)
                type_elem.set("class", "return_type")
                type_elem = self.parse_content(
                    type_elem, return_type_elem, context=d, **kwargs
                )

                type_elem = self.unnest_content(
                    type_elem,
                    unnest_elems={"p", "literal"},
                    **kwargs,
                )

                stripped_lines = []
                for line in type_elem.text:
                    stripped_lines.append(line.strip(" ."))

                type_elem.text = stripped_lines

                wrapper.append(type_elem)

            elem = Node("span", **d)  # E.p()
            elem.set("class", "return_value")
            wrapper.append(elem)
            elem = self.parse_content(elem, node, context=d, **kwargs)

            return wrapper

    def _parse_node_return_type(self, node, context=None, **kwargs):
        # Do nothing, because the `return_type` tag is also handled by the
        # `_parse_node_return_value` method.
        return None

    # def _parse_node_return_type(self, node, context=None, **kwargs):
    #     with DocTree("span", classes="return_type", **context) as d:
    #         elem = Node("span", **d)  # E.p()
    #         parsed = self.parse_content(elem, node, context=d, **kwargs)
    #         return parsed

    def _parse_node_block_quote(self, node, context=None, **kwargs):
        with DocTree("blockquote", **context) as d:
            elem = Node("blockquote", **d)  # E.p()
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
        objtype = node.get("objtype", "NONE")
        return self.extract_tree(node, subfunction=objtype, context=context, **kwargs)

    def _parse_node_definition_list(self, node, context=None, **kwargs):
        objtype = node.get("content-type", "NONE")
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

    def _parse_node_func_context(self, node, context=None, **kwargs):
        with DocTree("div", **context) as d:
            elem = Node("div", **d)  # E.div()
            elem.set("class", "context")

            for child in node:
                if (
                    extracted := self.extract_tree(child, context=d, **kwargs)
                ) is not None:
                    elem.append(extracted)

            return elem

    def _parse_node_desc_context(self, node, context=None, **kwargs):
        with DocTree(
            "h", indent_children=False, increment_heading=True, **context
        ) as d:
            elem = Node(
                "h", indent_children=False, increment_heading=True, **d
            )  # E.ol()
            elem.set("class", "context-name")
            parsed = self.parse_content(elem, node, context=d, **kwargs)
            # indented = parsed.indent()
            return parsed

    def _parse_node_desc_signature(self, node, context=None, **kwargs):
        sig_type = node.get("sig-type", None)
        if sig_type is not None:
            if sig_type == "enumerator":
                with DocTree("span", **context) as d:
                    node_wrapper = Node("span", **d)  # E.span()
                    node_wrapper.set("class", "enum-signature")

                    for item in node:
                        if (
                            extracted := self.extract_tree(item, context=d, **kwargs)
                        ) is not None:
                            node_wrapper.append(extracted)

                return node_wrapper

        else:
            with DocTree(
                "h", indent_children=False, increment_heading=True, **context
            ) as d:
                node_wrapper = Node("h", **d)  # E.span()
                node_wrapper.set("class", "signature include-toc")

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
            # ugly_dump(node)
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

    def _parse_node_desc_var(self, node, context=None, **kwargs):
        with DocTree("div", increase_heading=True, **context) as d:
            elem = Node("div", **d)  # E.div()
            elem.set("class", "struct-var")

            for child in node:
                if (
                    extracted := self.extract_tree(child, context=d, **kwargs)
                ) is not None:
                    elem.append(extracted)

            return elem

    def _parse_node_desc_struct(self, node, context=None, **kwargs):
        with DocTree("div", increase_heading=True, **context) as d:
            elem = Node("div", **d)  # E.div()
            elem.set("class", "struct")

            for child in node:
                if (
                    extracted := self.extract_tree(child, context=d, **kwargs)
                ) is not None:
                    elem.append(extracted)

            return elem

    def _parse_node_desc_enum(self, node, context=None, **kwargs):
        with DocTree("div", increase_heading=True, **context) as d:
            elem = Node("div", **d)  # E.div()
            elem.set("class", "enum")

            for child in node:
                if (
                    extracted := self.extract_tree(child, context=d, **kwargs)
                ) is not None:
                    elem.append(extracted)

            return elem

    def _parse_node_desc_enumerator(self, node, context=None, **kwargs):
        with DocTree("div", increase_heading=True, **context) as d:
            elem = Node("div", **d)  # E.div()
            elem.set("class", "enum-value")

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

    def _parse_node_struct_description(self, node, context=None, **kwargs):
        return self._parse_node_func_description(node, context=context, **kwargs)

    def _parse_node_enum_description(self, node, context=None, **kwargs):
        for child in node:
            if child.text and child.text == "Values:":
                node.remove(child)

        with DocTree("div", **context) as d:
            elem = Node("div", **d)  # E.ol()
            elem.set("class", "description")
            parsed = self.parse_content(elem, node, context=d, **kwargs)

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

    def _parse_node_definition_list_NONE(self, node, context=None, **kwargs):
        with DocTree("div", **context) as d:
            node_wrapper = Node("div", **d)  # E.span()
            # node_wrapper.set("class", "parameters")

            # with DocTree("h", increment_heading=True, **d) as d_h:
            #     node_wrapper.append(Node("h", "Parameters", **d_h))

            with DocTree("ul", **d) as d_ol:
                ol = Node("ul", **d_ol)
                parsed = self.parse_content(ol, node, context=d_ol, **kwargs)
                node_wrapper.append(parsed)
                # parsed._content[-1].tail += ")"

        return node_wrapper

    # def _parse_node_defin

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

        UNNESTABLE = set(kwargs.get("unnest_elems", UNNESTABLE))

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

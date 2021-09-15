import os
import sys
import tempfile
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from pprint import pprint
import typing as t

from docutils.core import publish_string
from lxml import etree
from lxml.builder import E
from sphinxcontrib.napoleon import Config as NapoleonConfig
from sphinxcontrib.napoleon.docstring import NumpyDocstring as NpDocstring

from .exceptions import ParsingError, UnknownStructureError, UnknownTagError
from .utils import (
    generate_frontmatter,
    partial_dump,
    ugly_dump,
    ugly_dump_if_contains,
    pptree,
    strtree,
)


def process_xml_nodes_to_html(parent_node):
    # Iterate through each of the XML-ified description that we converted from the
    # source `verbatim` reStructuredText block, and replace each XML element
    # with the appropriate HTML element.
    #
    # TODO: Properly handle the attributes present on the XML tags that control
    # rendering, such as `enumtype`, `suffix`, etc. on `enumerated_list`.
    for child in parent_node.iterdescendants():
        replacement_tag = None
        replacement_extras = {}
        if child.tag == "paragraph":  # or child.tag == "para":
            replacement_tag = "p"
        elif child.tag == "bullet_list":
            replacement_tag = "ul"
        elif child.tag == "enumerated_list":
            replacement_tag = "ol"
        elif child.tag == "list_item":
            replacement_tag = "li"
        elif child.tag == "title_reference":
            replacement_tag = "span"
            replacement_extras["class"] = "api-title-reference"
        elif child.tag == "emphasis":
            replacement_tag = "em"
        elif child.tag == "definition_list":
            replacement_tag = "dl"
        elif child.tag == "definition_list_item":
            for sub_elem in child.iterchildren(reversed=True):
                child.addnext(sub_elem)

            child.getparent().remove(child)
            continue
        elif child.tag == "term":
            if child.getparent().tag == "dl":
                replacement_tag = "dt"
        elif child.tag == "definition":
            if child.getparent().tag == "dl":
                replacement_tag = "dd"
        elif child.tag == "strong":
            # The <strong> tag in the XML input corresponds to the same HTML tag
            # in the output, but we still need to have a condition to ignore
            # it to avoid raising a RuntimeError.
            #
            # This behavior should be maintained, as this RuntimeError serves as
            # an indicator that this software needs to be updated to accomodate the input.
            continue
        elif replacement_tag is None:
            raise UnknownTagError(
                child,
                parent_node,
                "There is no known XML to HTML mapping for this tag.",
            )

        # If we have an XML tag that we can actually replace, we:
        #   - create a new empty tag,
        #   - add any leading `.text` from the original element,
        #   - add all of the original element's children to the new element, and
        #   - append the old element's tail if it has one.
        new_elem = E(replacement_tag)
        new_elem.text = child.text
        new_elem.extend(list(child))
        new_elem.tail = child.tail

        # If we have any extra attributes we want to append to the new element,
        # we do so here.
        for attrib, val in replacement_extras.items():
            if child_attrib := child.get(attrib) is not None:
                if attrib == "class":
                    new_elem.set(attrib, f"{child_attrib} {val}")
            else:
                new_elem.set(attrib, val)

        # Find our old XML element's parent and replace it with our new HTML.
        child.getparent().replace(child, new_elem)


def extract_fields_from_verbatim(
    detaileddescription_root: etree._Element,
    xml_fields: etree._Element,
) -> list:

    child_fields = list(xml_fields)
    if not len(child_fields):
        return None

    for child in child_fields:
        if child.tag not in {"docinfo"}:
            raise UnknownStructureError(child, xml_fields)

    docinfo_elem = xml_fields.find("docinfo")

    all_processed_fields = []
    field_list = list(docinfo_elem)
    for field_root in field_list:
        err_message = None
        if field_root.tag != "field":
            # err_message = f"The source XML tag `{field_root.tag}` is unknown."
            raise UnknownTagError(field_root)
        elif field_root.get("classes") is None:
            raise UnknownTagError(field_root, f"The `classes` attribute is missing.")
            # err_message = f"The `classes` attribute is missing."
        elif len(field_root.get("classes").split(" ")) > 1:
            # err_message = f"The field root has multiples `classes` values."
            raise UnknownTagError(
                field_root, f"The field root has multiples `classes` values."
            )

        # if err_message:
        #     raise RuntimeError(f"{err_message}\n\nNodes in error:\n{field_root}")

        field_class = field_root.get("classes")
        raw_field_name = field_root.find("field_name").text
        raw_field_body = field_root.find("field_body")

        process_xml_nodes_to_html(raw_field_body)

        processed_field = {
            "type": "",
            "name": "",
            "value": list(raw_field_body),
        }
        if raw_field_name.startswith("param "):
            processed_field["type"] = "param_desc"
            raw_param_name = raw_field_name.split(" ")[1]
            processed_field["name"] = raw_param_name
        elif raw_field_name.startswith("type "):
            processed_field["type"] = "param_type"

            raw_param_name = raw_field_name.split(" ")[1]
            processed_field["name"] = raw_param_name

            # for child_param in detaileddescription_root.iterchildren("param"):
            #     if (declname := child_param.find("declname")) is not None:
            #         if declname.text == raw_param_name:
            #             # We've found the right param
            #             param_type = field_root.find("field_body")[0].text
            #             declname.addprevious(E("type", param_type))
            #             # pptree(memberdef_root)
            #             break
        elif raw_field_name.startswith("raises "):
            processed_field["type"] = "func_raises"
            raw_param_name = raw_field_name.split(" ")[1]
            processed_field["name"] = raw_param_name
        elif raw_field_name == "returns":
            processed_field["type"] = "func_return_desc"
        elif raw_field_name == "rtype":
            processed_field["type"] = "func_return_type"
        else:
            raise ParsingError(
                "This rST-to-XML field is unknown.",
                field_root,
                detaileddescription_root,
            )

        all_processed_fields.append(processed_field)

    return all_processed_fields


def extract_description_from_verbatim(
    detaileddescription_root: etree._Element,
    xml_desc: etree._Element,
) -> None:
    """Process the detailed description field from a verbatim block.

    Parameters
    ----------
    detaileddescription_root : etree._Element
        DESCRIPTION_OF_ITEM
    xml_desc : etree._Element
        DESCRIPTION_OF_ITEM
    """

    # # We're started from inside the `verbatim` object, so the first thing
    # # we should do if find the `detaileddescription` node's parent. This will
    # # allow us to easily swap out that object with our own re-processed version.
    # detaileddesc_elem = None
    # detaileddesc_parent = None
    # for elem in verbatim_obj.iterancestors(tag="detaileddescription"):
    #     detaileddesc_elem = elem
    #     detaileddesc_parent = detaileddesc_elem.getparent()
    #     break

    # if detaileddesc_parent is None:
    #     return

    # When we converted from the source `verbatim` reStructuredText block, it added
    # XML nodes that differ from HTML tags. This will replace each XML element
    # with the appropriate HTML element.
    process_xml_nodes_to_html(xml_desc)

    # We want to replace the existing `detaileddescription` node, so we create a
    # new blank one, then attach all of the elements we just converted (which are
    # still attached to the `xml_desc` variable).
    new_desc = E("longdescription")
    new_desc.extend(list(xml_desc))
    # detaileddesc_parent.replace(detaileddesc_elem, new_desc)
    # detaileddesc_elem.insert(0, new_desc)
    return new_desc


# def process_verbatim_fields(root_node):
def strip_verbatim_from_detaileddescription(detaileddescription_root):
    verbatims = detaileddescription_root.xpath(".//verbatim")

    for verbatim in verbatims:
        print("-------------------------------------------------------")
        # print([_.tag for _ in verbatim.iterancestors()])

        # # We want to get the `memberdef` object that enclosed this `verbatim`
        # # block to be easily accessible in the future, so grab a reference to
        # # it right now.
        # memberdef_root = None
        # for elem in verbatim.iterancestors(tag="memberdef"):
        #     memberdef_root = elem
        #     break

        verbatim_text = verbatim.text.split("\n")
        padding_len = len(verbatim_text[0]) - len(verbatim_text[0].lstrip(" "))

        # pprint(verbatim_text)
        # break

        section_delim = "".join([" "] * padding_len + ["---"])

        desc_end = -1
        unindented_lines = []
        for ix, line in enumerate(verbatim_text):
            if desc_end == -1 and line.startswith(section_delim):
                desc_end = ix - 1

            unindented_lines.append(line[padding_len:])

        verbatim_desc = "\n".join(unindented_lines[0:desc_end])
        verbatim_fields = "\n".join(unindented_lines[desc_end:-1])

        rst_desc = str(NpDocstring(verbatim_desc, what="method"))
        rst_fields = str(NpDocstring(verbatim_fields, what="method"))

        xml_desc = etree.fromstring(publish_string(rst_desc, writer_name="xml"))
        xml_fields = etree.fromstring(publish_string(rst_fields, writer_name="xml"))

        # pptree(xml_desc)
        # pptree(xml_fields)
        # break

        # process_python_description(verbatim, xml_desc)
        # process_python_other_fields(memberdef_root, xml_fields)
        longdescription_elem = extract_description_from_verbatim(
            detaileddescription_root,
            xml_desc,
        )

        extracted_fields = extract_fields_from_verbatim(
            detaileddescription_root,
            xml_fields,
        )

        # Once we have extracted the content of the `verbatim` object, we
        # don't need to keep it in our tree anymore, so it should be deleted.
        verbatim_parent_elem = None
        elem_to_remove = None
        if verbatim.getparent().tag == "para":
            elem_to_remove = verbatim.getparent()
            verbatim_parent_elem = elem_to_remove.getparent()
        else:
            elem_to_remove = verbatim
            verbatim_parent_elem = elem_to_remove.getparent()

        if elem_to_remove:
            verbatim_parent_elem.remove(elem_to_remove)

        detaileddescription_root.append(longdescription_elem)

        # if memberdef_root:
        #     pptree(memberdef_root)

import os, sys
import io
from datetime import datetime

from ruamel.yaml import YAML
from ruamel.yaml.compat import StringIO

from pprint import pprint
from copy import deepcopy

from lxml import etree
from lxml.builder import E

from .utils import (
    generate_frontmatter,
    partial_dump,
    ugly_dump,
    ugly_dump_if_contains,
    pptree,
    strtree,
)


class ParsingError(RuntimeError):
    def __init__(self, message, unknown_node, parent_node=None):

        full_message = []
        full_message.append(message)
        full_message.append(
            f"The Hugoify tool is unsure how this tag should be processed. Please add "
            f"handler code for this tag where this exception was raised."
        )

        full_message.append(f"Unknown tag: {unknown_node.tag}")

        if parent_node is not None:
            full_message.append(f"Enclosing tag: {parent_node.tag}")

        full_message.append(f"Erroneous XML:")

        if parent_node is None:
            full_message.append("    " + strtree(unknown_node, 1))
        else:
            full_message.append("    " + strtree(parent_node, 1))

        joined_message = "\n".join(full_message)
        RuntimeError.__init__(self, joined_message)


class UnknownTagError(ParsingError):
    def __init__(
        self,
        unknown_node: etree._Element,
        parent_node: etree._Element = None,
        message: str = None,
    ):
        msg = f"The source XML tag <{unknown_node.tag}> is unknown in this context."

        if message is not None:
            msg = f"{msg} {message}"
        ParsingError.__init__(self, msg, unknown_node, parent_node)


class UnknownStructureError(ParsingError):
    def __init__(
        self,
        unknown_node: etree._Element,
        parent_node: etree._Element = None,
        message: str = None,
    ):
        msg = f"The structure beginning with the <{unknown_node.tag}> tag is unknown in this context."
        if message is not None:
            msg = f"{msg} {message}"
        ParsingError.__init__(self, msg, unknown_node, parent_node)

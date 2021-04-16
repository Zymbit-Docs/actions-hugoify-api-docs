import os, sys
import io
from datetime import datetime

from ruamel.yaml import YAML
from ruamel.yaml.compat import StringIO

from pprint import pprint
from copy import deepcopy

from lxml import etree
from lxml.builder import E


class Frontmatter:
    def __init__(self, **kw):
        self.yaml = YAML()
        self.yaml.explicit_start = True
        self.yaml.width = 4096
        self.yaml.indent(mapping=4, sequence=2, offset=4)

    def generate(self, data, stream=None, **kw):
        data.update(
            {
                "draft": False,
                "images": [],
                "type": "docs",
                "layout": "single",
                "weight": 0,
                "toc": True,
            }
        )
        inefficient = False

        if stream is None:
            inefficient = True
            stream = StringIO()

        self.yaml.dump(data, stream, **kw)

        stream.write("---\n")
        if inefficient:
            return stream.getvalue()


generate_frontmatter = Frontmatter(typ="safe")


def _reserialize(tree, indent=True):
    new_tree = deepcopy(tree)
    serialized = etree.tostring(new_tree, encoding="utf-8").decode("utf-8")

    unserialized = etree.fromstring(serialized, parser=etree.XMLParser(recover=True))
    if indent:
        etree.indent(unserialized, space="  ", level=0)

    return unserialized


def _serialize(tree):
    unserialized = _reserialize(tree)
    return etree.tostring(
        unserialized,
        encoding="utf-8",
        pretty_print=True,
    ).decode("utf-8")


def unserialize(content):
    return etree.fromstring(str(content), parser=etree.XMLParser(recover=True))


def verbose_dump(tree, dump_meta=None, count=2500):
    serialized = _serialize(tree)
    if count is None or count == 0:
        count = len(serialized)

    print("=====================================================================")
    print("Dumping:")
    print(f"  - tag:           {tree.tag}")

    if dump_meta:
        for key, val in dump_meta.items():
            print("  - {: <15}{}".format(f"{key}:", val))
    print("---------------------------------------------------------------------")
    print(serialized[:count], end="|✖\n")
    print("=====================================================================")


def partial_dump(tree, count=1000):
    serialized = _serialize(tree)
    print(serialized[:count], end="")


def ugly_dump(tree, count=1000):
    print("↓↓↓↓↓↓↓↓↓↓↓")
    print(
        etree.tostring(
            _reserialize(tree),
            encoding="utf-8",
            pretty_print=False,
        ).decode("utf-8")[:count],
        end="",
    )
    print("✖✖✖")


def ugly_dump_if_contains(tree, contains, count=1000):

    if tree is None:
        return None

    dumped = etree.tostring(
        tree,
        encoding="utf-8",
        pretty_print=False,
    ).decode("utf-8")

    if dumped.find(contains) > -1:
        print("↓↓↓↓↓↓↓↓↓↓↓")
        print(dumped, end="")
        print("✖✖✖")

        return dumped

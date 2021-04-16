import os, sys
from pathlib import Path
from lxml import etree
from lxml.builder import E
from lxml.html import HtmlElement
import lxml.html.builder as html_builder

from copy import deepcopy

from pprint import pprint

from .utils import partial_dump, ugly_dump, verbose_dump, unserialize, _reserialize

from typing import Union, List
from contextlib import contextmanager
from collections.abc import MutableMapping

from functools import partial


class DocTree(MutableMapping):
    INDENT_SIZE = 4
    HERITABLE_KEYS = {
        "parent_context",
        "class_path",
        "full_path",
        "indent_level",
        "_heading_level",
        "_indent_children",
        "_opening_newline",
        "_newline_tail",
        "_increase_indent",
    }

    def __init__(
        self,
        add_path,
        /,
        add_class: str = None,
        *,
        heading_level: int = None,
        increment_heading: bool = None,
        parent_context: object = None,
        increase_indent: bool = True,
        indent_level: int = -1,
        indent_children: bool = True,
        opening_newline: bool = True,
        newline_tail: bool = True,
        **kwargs,
    ):
        # self.kwargs = deepcopy(kwargs)
        self._indent_children = indent_children
        self._opening_newline = opening_newline
        self._newline_tail = newline_tail

        if heading_level and increment_heading:
            raise ValueError(
                "Keyword args `heading_level` and `increment_heading` are mutually exclusive."
            )

        if heading_level is None:
            if (_heading_level := kwargs.get("_heading_level", None)) is not None:
                self.heading_level = _heading_level
            elif parent_context is not None:
                # If we haven't manually passed a heading level, get it from the parent context.
                self.heading_level = parent_context.heading_level
            else:
                # If the parent context doesn't exist, set the heading level to 1
                self.heading_level = 1
        else:
            # If we have passed a heading level, just set that manually.
            self.heading_level = heading_level

        if increment_heading is None:
            if add_path == "h":
                # If we haven't specified whether the heading should be incremented, if we're
                # creating a heading, we do want to increment it automatically.
                self.increment_heading = True
            else:
                # If we haven't specified whether the heading should be incremented, for all
                # other tags, we should increment it.
                self.increment_heading = False
        else:
            # If we manually specify whether or not we should increment the heading,
            # use that setting.
            self.increment_heading = increment_heading

        # Increment the heading based on the setting we passed in.
        if self.increment_heading:
            self.heading_level += 1

        self._heading_level = self.heading_level

        if parent_context is None:
            self.class_path = []
            self.full_path = []
        else:
            self.class_path = parent_context.classes
            self.full_path = parent_context.path

        self.parent_context = self

        self._increase_indent = increase_indent
        if self._increase_indent:
            self.indent_level = indent_level + 1

        if add_path == "h":
            self._current_path_level = f"h{self.heading_level}"
        else:
            self._current_path_level = add_path

        # self.kwargs["heading_level"] = self.heading_level
        # self.kwargs["indent_level"] = self.indent_level

        # self.heading_level += 1
        # add_path = f"h{self.heading_level}"

        self.full_path.append(add_path)
        # self.kwargs["parent_context"] = self

        # pprint(self.__dict__)

    def __enter__(self):
        if self._current_path_level is not None:
            self.class_path.append(self._current_path_level)
        return self

    def __exit__(self, type, value, traceback):
        if self._current_path_level is not None:
            self.class_path.pop(-1)

        self.full_path.pop(-1)

        if self.increment_heading:
            self.heading_level -= 1

        if self._increase_indent:
            self.indent_level -= 1

    def add_hang(self, node):
        indentation = (" " * self.INDENT_SIZE) * self.indent_level
        hanging_indent = f"\n{indentation}"

        if node.text:
            node.text = f"{hanging_indent}{node.text}"
        else:
            node.text = hanging_indent

    def add_tail(self, node):
        indentation = (" " * self.INDENT_SIZE) * (self.indent_level - 1)
        hanging_indent = f"\n{indentation}"

        if node.tail:
            node.tail = f"{hanging_indent}{node.tail}"
        else:
            node.tail = hanging_indent

    @property
    def classes(self):
        return self.class_path

    @property
    def class_list(self):
        return " ".join(self.class_path)

    @property
    def path(self):
        return self.full_path

    def __len__(self):
        return len(self.keys())

    def __getitem__(self, key):
        # return self.__dict__[key]
        if key in self.keys():
            return self.__dict__[key]
        else:
            raise AttributeError(f"Attribute {key} is not accessible.")

    def __setitem__(self, key, value):
        # self.__dict__[key] = value
        if key in self.HERITABLE_KEYS:
            self.__dict__[key] = value
        else:
            raise AttributeError(f"Attribute {key} is not accessible.")

    def __delitem__(self, key):
        # del self.__dict__[key]
        if key in self.keys():
            del self.__dict__[key]
        else:
            raise AttributeError(f"Attribute {key} is not accessible.")

    def __iter__(self):
        # return iter(self.__dict__)
        return iter(self.keys())

    def __contains__(self, item):
        # return item in self.__dict__
        return item in self.keys()

    def keys(self):
        return [k for k in self.__dict__.keys() if k in self.HERITABLE_KEYS]

    def items(self):
        return {k: self[k] for k in self.keys()}


class Node(HtmlElement):
    def __init__(self, tag, /, children=None, *, classes=None, **kwargs):
        for key in DocTree.HERITABLE_KEYS:
            if key in kwargs:
                self.__dict__[key] = kwargs[key]
            else:
                self.__dict__[key] = None

        if self.indent_level is None:
            self.indent_level = 0

        _if_indent = kwargs.get("_indent_children", None)
        if _if_indent is None or _if_indent == False:
            self._indent_children = False

        if tag == "h":
            tag = f"h{kwargs.get('_heading_level', 2)}"
        self._elem = E(tag)
        self.__self__ = self._elem
        self._content = []
        self._text = []
        self._tail = []
        self._newlines = 1

        try:
            self._render_empty = kwargs.get("render_empty")
            del kwargs["render_empty"]
        except KeyError:
            self._render_empty = False

        self._classes = []
        if type(classes) is list:
            self._classes = deepcopy(classes)
        elif type(classes) is str:
            self._classes.extend(classes.split(" "))

        if (newlines := kwargs.get("newlines", False)) :
            self._newlines = newlines

        if children is not None:
            self.append(children)
        else:
            self._content = []

        # self._kwargs = deepcopy(kwargs)

        # pprint(self.__dict__)

        # pprint(self.__dict__)

    # def __call__(self, tag, classes=None, **kwargs):
    #     node = NodeBuilder(tag, classes=classes, **kwargs)
    #     return node

    @property
    def text(self):
        return self.__text_getter("_text")

    @text.setter
    def text(self, new_text):
        self.__text_setter("_text", new_text)

    @text.deleter
    def text(self):
        self._text = []

    @property
    def tail(self):
        return self.__text_getter("_tail")

    @tail.setter
    def tail(self, new_text):
        self.__text_setter("_tail", new_text)

    @tail.deleter
    def tail(self):
        self._tail = []

    def __text_getter(self, which):
        return self.__dict__[which]

    def __text_setter(self, which, new_text):
        self.__dict__[which] = []

        if new_text == "" or new_text is None:
            return

        if type(new_text) is str:
            self.__dict__[which].append(new_text)
        elif type(new_text) is list:
            self.__dict__[which].extend(new_text)
        else:
            raise ValueError(f"Invalid type: {type(new_text)}")

    def append(self, obj, **kwargs):
        if type(obj) is str:
            if not self._content:
                self._text.append(obj)
            else:
                raise RuntimeError("Text cannot be appended to a node with children.")
        elif type(obj) is list:
            for item in obj:
                self.append(item, **kwargs)
        elif isinstance(obj, Node):
            self._content.append(obj)
        else:
            raise ValueError(f"Invalid type: {type(obj)}")

    def add_text(self, obj, **kwargs):
        if type(obj) is str:
            self._text.append(obj)
        elif type(obj) is list:
            for item in obj:
                self.add_text(item, **kwargs)
        else:
            raise ValueError(f"Invalid type: {type(obj)}")

    def set(self, key, val):
        self._elem.set(key, val)

    def indent(self, space="    ", level=0):
        elem_copy = deepcopy(self)
        # etree.indent(elem_copy, space=space, level=level)
        etree.indent(elem_copy.__self__, space=space, level=level)

        return elem_copy

    def __deepcopy__(self, memo):
        node_copy = Node(self.tag)
        node_copy.__self__ = deepcopy(self.__self__)
        for key, val in self.__dict__.items():
            if key in {"__self__", "_kwargs"}:
                continue

            node_copy.__dict__[key] = deepcopy(val)

        # node_copy._newlines = self._newlines
        return node_copy

    @property
    def class_list(self):
        return " ".join(self._classes)

    def raw(self):
        elem = deepcopy(self.__self__)

        # print(elem.tag, elem.items(), self._indent_children)
        # pprint(elem.__dict__)
        # if self._opening_newline and len(self._content):
        elem.text = "".join(self._text)
        # if self._indent_children and len(self._content):
        #     elem.text += "\n" + (" " * DocTree.INDENT_SIZE) * self.indent_level

        for ix, child in enumerate(self._content):
            child_raw = child.raw()

            # if self._indent_children:
            #     etree.indent(child_raw, space="    ", level=self.indent_level)
            # else:
            #     etree.indent(child_raw, space="")

            if not child_raw.tail:
                child_raw.tail = ""

            # if self._indent_children:
            #     if ix < len(self._content) - 1:
            #         child_raw.tail += (
            #             "\n" + (" " * DocTree.INDENT_SIZE) * self.indent_level
            #         )
            #     else:
            #         child_raw.tail += "\n"

            elem.append(child_raw)
        # elem.extend([_.raw() for _ in self._content])

        # if self._kwargs.get("newline_tail", True):
        #     elem.tail = "\n"
        elem.tail = "".join(self._tail)
        # if self._newline_tail:
        #     elem.tail += "\n"
        # if self._indent_children:
        #     elem.tail += "\n" + (" " * DocTree.INDENT_SIZE) * self.indent_level

        # if self._indent_children:
        #     etree.indent(elem, space="    ", level=0)  # level=self.indent_level)

        if (classes := self.class_list) :
            elem.set("classes", classes)

        return elem

    @property
    def tag(self):
        return self._elem.tag

    def items(self):
        return self._elem.items()

    def __len__(self):
        return len(self._content)

    def __iter__(self):
        return iter(self._content)

    def __getattr__(self, name):
        if name in self._elem:
            child_func = getattr(self._elem, name, None)
            return child_func
        else:
            raise AttributeError(f"Attribute not found: {name}")

    def __str__(self):
        raw = self.raw()
        # etree.indent(raw, space="    ", level=self.indent_level)
        return etree.tostring(raw, encoding="unicode")


# Node = NodeBuilder()

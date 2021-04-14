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


class DocPath(MutableMapping):
    # CURRENT_PATH: list[str] = []

    def __init__(self, add_path, **kwargs):
        self.kwargs = deepcopy(kwargs)
        self.current_division = add_path

        self.parent_context = self.kwargs.get("parent_context", None)
        if self.parent_context is None:
            self.current_path = []
        else:
            self.current_path = self.parent_context.current_path

        self.heading_level = self.kwargs.get("heading_level", 2)

        self.increment_heading = self.kwargs.get("increment_heading", False)
        if self.increment_heading:
            # print("Incrementing heading!")
            self.heading_level += 1
            del self.kwargs["increment_heading"]

        self.kwargs["heading_level"] = self.heading_level

        self.current_path.append(add_path)
        self.kwargs["parent_context"] = self

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.current_path.pop(-1)

        if self.increment_heading:
            self.heading_level -= 1

    @property
    def classes(self):
        return self.current_path

    def __len__(self):
        return len(self.kwargs)

    def __getitem__(self, key):
        return self.kwargs[key]

    def __setitem__(self, key, value):
        self.kwargs[key] = value

    def __delitem__(self, key):
        del self.kwargs[key]

    def __iter__(self):
        return iter(self.kwargs)

    def __contains__(self, item):
        return item in self.kwargs


class Node(HtmlElement):
    def __init__(self, tag=None, classes=None, **kwargs):
        self._content = []
        self._text = []
        self._tail = []
        self._newlines = 1
        self._pending = None

        try:
            self._render_empty = kwargs.get("render_empty")
            del kwargs["render_empty"]
        except KeyError:
            self._render_empty = False

        if tag is None:
            self._elem = None
        else:
            self._elem = E(tag)

            self._classes = []
            if type(classes) is list:
                self._classes = deepcopy(classes)
            elif type(classes) is str:
                self._classes.extend(classes.split(" "))

            if (newlines := kwargs.get("newlines", False)) :
                self._newlines = newlines

    @property
    def classes(self):
        return " ".join(self._classes)

    @property
    def text(self):
        # for _ in self._text:
        #     print("Element:", type(_), _)
        return "".join([str(_) for _ in self._text])

    @text.setter
    def text(self, new_text):
        if type(new_text) is tuple:
            # print("Processing tuple: ", new_text)
            self.append((new_text[0], 0))

            if type(new_text[1]) is list:
                for item in new_text[1]:
                    self.append(item)
        else:
            # print("Appending text:", new_text)
            self._text.append(new_text)

    @text.deleter
    def text(self):
        self._text = []

    @property
    def tail(self):
        return "".join(self._tail)

    @tail.setter
    def tail(self, new_text):
        self._tail.append(new_text)

    @tail.deleter
    def tail(self):
        self._tail = []

    @property
    def content(self):
        return self._content

    def append(self, obj, **kwargs):
        if self._pending is not None:
            pending_obj, pending_kwargs = self._pending
            self._pending = None
            self.append(pending_obj, **pending_kwargs)

        not_last = kwargs.get("not_last", False)
        if not_last:
            del kwargs["not_last"]
            self._pending = (obj, kwargs)
            return

        if type(obj) is list:
            for item in obj:
                self.append(item, **kwargs)
        elif isinstance(obj, TextNode):
            print("Processing:", obj.text)
            self._content.append(obj)
        elif type(obj) is tuple:
            node = Node(tag=None, newlines=obj[1])
            node.text = obj[0]
            self._content.append(node)
        else:
            self._content.append(obj)

    @property
    def elem(self):
        if not self._render_empty:
            if not self.text and self._content == []:
                return ""

        if self._elem is not None:
            e = deepcopy(self._elem)
            e.set("class", self.classes)
            e.text = self.text

            for node in self._content:
                next_elem = node.elem
                if next_elem != "":
                    print(next_elem)
                    e.append(next_elem.elem)

            e.tail = self.tail

            return e
        else:
            return self.text

    def __str__(self):
        if isinstance(self, TextNode):
            return self.text

        elem = self.elem

        if type(elem) is str:
            return elem
        else:
            return etree.tostring(elem, encoding="utf-8").decode("utf-8")


class TextNode(Node):
    def __init__(self, text, newlines: int = 1, **kwargs):
        super().__init__(tag=None, newlines=newlines, **kwargs)

        for key, val in kwargs.items():
            object.__dict__[key] = deepcopy(val)

        # If we're passing a TextNode into this object, we can just copy the
        # contents of that Textnode into this one.
        if isinstance(text, TextNode):
            self._content.extend(text.elem)

        # If we're passing a normal Node into this object, create a TextNode
        # out of each sub-element and add it to this text node.
        elif isinstance(text, Node):
            self._content.extend([TextNode(_, newlines, **kwargs) for _ in text._text])

        # If we've been passed a list, create a TextNode for each list item
        # and add it to this text node.
        elif type(text) is list:
            for item in text:
                self._content.append(TextNode(item, newlines, **kwargs))

        # If we've been passed a string, just add it to the element.
        elif type(text) is str:
            self._text = text

        # Throw an error for any other type.
        else:
            raise ValueError(f"TextNode cannot accept {type(text)} as a value.")

    @property
    def elem(self):
        e = E("TextNode")
        e.text = self.text

        for node in self._content:
            next_elem = node.elem
            if next_elem != "":
                print(next_elem)
                e.append(next_elem.elem)

        e.tail = self.tail

        return e

    @property
    def text(self):
        return self._text

    def __str__(self):
        full_elem = self.elem

        if full_elem.tag == "TextNode":
            full_text = []

            full_text.append(full_elem.text)
            for child in full_text:
                full_text.append(str(child))

            if full_elem.tail:
                full_text.append(full_elem.tail)

            return "".join(full_text)
        else:
            return etree.tostring(full_elem, encoding="utf-8").decode("utf-8")

    def __repr__(self):
        return self.text

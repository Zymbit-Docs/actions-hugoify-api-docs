import os, sys
import io
from datetime import datetime

from ruamel.yaml import YAML
from ruamel.yaml.compat import StringIO

from pprint import pprint


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

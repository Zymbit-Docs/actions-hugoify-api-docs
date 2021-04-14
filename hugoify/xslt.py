import os, sys
from pathlib import Path
from lxml import etree
from lxml.builder import E

from copy import deepcopy

from pprint import pprint

from .utils import partial_dump, ugly_dump, verbose_dump, unserialize, _reserialize

PWD = (Path(__file__).resolve()).parent


def get_abs(relative):
    return str(PWD / relative)


def xslt():
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
        self.extensions = {
            ("testns", "abstract"): Abstract(),
        }

        print(f"Processing {str(input_file)}...")

        self.input_file = input_file.resolve()

        self.rendered_file = output_dir / f"{self.input_file.stem}.md"
        self.rendered_tree = E("root")
        self.rendered_document = []

        tree = etree.parse(
            str(self.input_file),
            parser=etree.XMLParser(load_dtd=True, no_network=False, recover=True),
        )
        self.document_root = _reserialize(tree.getroot())

        frontmatter = etree.XSLT(
            etree.parse(get_abs("xslt/frontmatter.xslt")), extensions=self.extensions
        )
        generated_frontmatter = str(frontmatter(tree.getroot())).lstrip()
        with self.rendered_file.open("w") as f:
            f.write(generated_frontmatter)

        self.parse_section(self.document_root.xpath("./section"))

        # result_tree = transform(tree.getroot())
        with self.rendered_file.open("a") as fp:
            for line in self.rendered_document:
                if line == "\n":
                    fp.write(line)
                else:
                    fp.write(f"{line}\n")
            # for block in self.rendered_document:
            #     etree.indent(block, space="    ", level=0)
            #     fp.write(etree.tostring(block, encoding="unicode"))
            #     fp.write("\n")

    def transform(self, tree, xslt="rendered"):
        transformer = etree.XSLT(
            etree.parse(get_abs(f"xslt/{xslt}.xslt"))  # , extensions=self.extensions
        )

        # ugly_dump(tree)
        verbose_dump(tree)

        transformed = str(transformer(_reserialize(tree)))

        segments = transformed.partition("\n")
        if segments[0].find("<!DOCTYPE") == 0:
            return segments[2]
        else:
            return transformed

    def add_lines(self, block):
        if type(block) is list:
            self.rendered_document.extend(block)
        elif type(block) is str:
            line = block.split("\n")
            self.rendered_document.extend(line)

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
            self.add_lines([f"## {section_title}\n"])

        for child in root:
            self.add_lines(self.parse_node(child))

        # self.rendered_document.append(self.transform(root))
        # # print(self.transform(root))

    def parse_node(self, root):
        if type(root) is list:
            return [self.parse_node(_) for _ in root]

        if root.tag == "paragraph":
            return root.text.strip() + "\n"
        elif root.tag == "enumerated_list":
            return self.__parse_enumerated_list(root)
        elif root.tag == "desc" and root.get("objtype") == "class":
            return self.__parse_class(root)

    def __parse_class(self, root):
        transformed = self.transform(root, xslt="classes")
        return transformed
        # for elem in root:
        #     return self.transform(elem, xslt="classes")

    def __parse_enumerated_list(self, root):
        items = []
        for list_item in root.xpath("./list_item"):
            parsed = self.parse_node(list(list_item))
            sub_items = " ".join(_.strip() for _ in parsed)

            items.append(f"1. {sub_items}")

        items.append("\n")

        return items


class CustomElement(etree.XSLTExtension):
    def __init__(self, ext_name="", xslt_file=None, **kwargs):
        self.ext_meta = {"ext_name": ext_name}

        if xslt_file:
            self.xslt_file = xslt_file

        for key, val in kwargs:
            self.ext_meta[key] = val

        if not hasattr(self, "xslt_file"):
            renderer_name = self.ext_meta["ext_name"]
            if renderer_name:
                possible_xslt = PWD / "xslt" / f"{ext_name}.xslt"
                if possible_xslt.exists():
                    self.xslt_file = str(possible_xslt)

        self.__transform = etree.XSLT(etree.parse(self.xslt_file))

    def transform(self, tree):
        return self.__transform(deepcopy(tree))

    def execute(self, context, self_node, input_node, output_parent):
        # just copy own content input to output
        # output_parent.extend(list(self_node))

        # verbose_dump(output_parent)
        # dir(output_parent)
        # help(output_parent)
        transformed = self.transform(input_node)
        output_parent.text = str(transformed)
        # verbose_dump(unserialize(transformed))
        # output_parent.append(self.transform(input_node))

        # verbose_dump(self_node, self.ext_meta)
        # verbose_dump(input_node, self.ext_meta)
        # verbose_dump(output_parent, self.ext_meta)


class Abstract(CustomElement):
    def __init__(self):
        super().__init__(ext_name="abstract")

    def execute(self, context, self_node, input_node, output_parent):
        super().execute(context, self_node, input_node, output_parent)


class Frontmatter(CustomElement):
    def __init__(self):
        super().__init__(ext_name="frontmatter")

    def execute(self, context, self_node, input_node, output_parent):
        super().execute(context, self_node, input_node, output_parent)

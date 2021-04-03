# from .markdownify import main
import os, sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from lxml import etree
from lxml.builder import E

from .utils import generate_frontmatter

from pprint import pprint


def partial_dump(tree, count=500):
    print(
        etree.tostring(tree, encoding="utf-8", pretty_print=True,).decode(
            "utf-8"
        )[:count],
        end="",
    )


def ugly_dump(tree, count=1000):
    print("↓↓↓↓↓↓↓↓↓↓↓")
    print(
        etree.tostring(tree, encoding="utf-8", pretty_print=False,).decode(
            "utf-8"
        )[:count],
        end="",
    )
    print("✖✖✖")


def main():
    input_dir = Path(os.environ["INPUT_RAWPATH"])
    output_dir = Path(os.environ["INPUT_OUTPUTPATH"])

    if not input_dir.exists():
        print("Exiting because there are no files to process...")
        sys.exit(0)

    for f in input_dir.glob("*.xml"):
        print(f"Processing {str(f)}...")

        tree = etree.parse(
            str(f), parser=etree.XMLParser(recover=True, remove_comments=True)
        )
        root = tree.getroot()

        remove_attrs = [
            "noemph",
            "{*}space",
            "add_permalink",
            "is_multiline",
            "noindex",
        ]
        etree.strip_attributes(
            root,
            *remove_attrs,
        )

        body = root.find("section")
        contents = CodeFile(body)
        contents.parse()
        # frontmatter, parsed = parse_file(f)

        output_xml = f.parents[1] / "output" / f"{f.stem}.xml"

        with output_xml.open("w") as fp:
            doc = E.document()
            doc.extend(root.find("./section").getchildren())
            etree.indent(doc, space="    ", level=0)
            fp.write(etree.tostring(doc, encoding="unicode"))
            fp.write("\n")

        print()

    sys.exit(0)


def extract_text(elem):
    return str(elem.text).strip()


class CodeFile(object):
    DOMAIN_C = 1
    DOMAIN_CPP = 2
    DOMAIN_PY = 5

    def __init__(self, root):
        self.root = root
        self.frontmatter = None
        self.domain = None

        section_name = self.root.get("names").split(" ")[0]
        if section_name.find("python") > -1:
            self.domain = self.DOMAIN_PY
        elif section_name.find("c++") > -1:
            self.domain = self.DOMAIN_CPP
        elif section_name.find("c") > -1:
            self.domain = self.DOMAIN_C

        print(f"Parsing domain: {self.domain}")

    @staticmethod
    def unnest_paragraphs(elems, unnested: list = None, dropped_elems: list = None):
        if unnested is None:
            unnested = []
        if dropped_elems is None:
            dropped_elems = []

        for elem in elems:
            if elem.tag == "paragraph":
                subnest = list(elem.getchildren())
                if len(subnest):
                    CodeFile.unnest_paragraphs(subnest, unnested)
                else:
                    unnested.append(deepcopy(elem))
            else:
                unnested.append(deepcopy(elem))

            dropped_elems.append(elem)

        return unnested, dropped_elems

    def parse(self):
        self.preparser_format()
        self.generate_frontmatter()
        self.parse_intro()
        # return
        if self.domain == self.DOMAIN_CPP:
            self._parse_cpp()

        self.tidy_tree()

    def preparser_format(self):
        for elem in self.root.xpath(".//paragraph"):
            if len(elem):
                continue

            lines = elem.text.split("\n")
            new_text = " ".join([_.strip() for _ in lines])

            elem.text = new_text

    def generate_frontmatter(self):
        title_elem = self.root.find("./title")
        page_title = extract_text(title_elem)
        page_description = extract_text(self.root.find("./paragraph"))
        timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")

        metadata: dict = {
            "title": page_title,
            "description": page_description,
            "lastmod": timestamp,
        }

        self.frontmatter = generate_frontmatter.generate(metadata)
        self.root.remove(title_elem)

    def parse_intro(self):
        if self.domain == self.DOMAIN_C:
            intro_tree = self.root.xpath("./container/preceding-sibling::paragraph")
        else:
            intro_tree = self.root.xpath("./desc[1]/preceding-sibling::*")

        intro_elems = []
        for elem in intro_tree:
            if elem.tag in ("paragraph", "enumerated_list"):
                intro_elems.append(elem)

        unnested_elems = []
        elems, dropped_elems = self.unnest_paragraphs(intro_elems)
        for elem in elems:
            if elem.tag == "definition_list":
                dropped_elems.append(elem)
            else:
                unnested_elems.append(elem)

        for drop_elem in dropped_elems:
            try:
                self.root.remove(drop_elem)
            except ValueError:
                pass

        intro_section = E.section(id="abstract")
        intro_section.extend(unnested_elems)
        self.root.insert(0, intro_section)
        # for ix, _ in enumerate(unnested_elems):
        #     self.root.insert(ix, _)

    def tidy_tree(self):

        for elem in self.root.xpath(".//index"):
            parent = elem.find("..")
            parent.remove(elem)

        for elem in self.root.xpath(".//desc_signature"):
            ids = elem.get("ids")
            if ids:
                new_id = ids.split(" ")[-1]
                new_id = new_id.strip()

                elem.set("ids", new_id)

        for elem in self.root.xpath("//paragraph"):
            if elem.text and len(elem.text.strip()):
                continue
            if elem.tail and len(elem.tail.strip()):
                continue

            children = [deepcopy(_) for _ in elem.getchildren()]
            if not len(children):
                continue

            parent = elem.find("..")

            curr_ix = parent.index(elem)
            parent.remove(elem)

            for ix, _ in enumerate(children):
                parent.insert(curr_ix + ix, _)

        terms_xpath = "//term[count(./*)<2 and ./strong]"
        for elem in self.root.xpath(terms_xpath):
            etree.strip_tags(elem, "strong")
            elem.text = elem.text.strip()

    def _parse_cpp(self):
        if self.domain != self.DOMAIN_CPP:
            raise RuntimeError("_parse_cpp can only be called on C++ definitions.")

        # Remove the namespace wrapper
        namespace_wrappers = self.root.xpath("./desc[@desctype='type']")
        for wrapper in namespace_wrappers:
            namespace_contents = wrapper.xpath(
                "./desc_signature[./desc_signature_line/target[contains(@ids, 'namespace')]]"
                "/following-sibling::desc_content[1]/*"
            )

            ix = self.root.index(wrapper)
            for elem in namespace_contents:
                self.root.insert(ix, deepcopy(elem))
                ix += 1

            self.root.remove(wrapper)

        for elem in self.root.xpath(".//desc_signature_line/target"):
            return_elem = E.desc_returns(elem.tail.strip())
            parent = elem.find("..")
            parent.replace(elem, return_elem)

        # Move typedefs to a dedicated section
        typedef_section = E.section(id="typedefs")
        typedef_xpath = self.root.find("./container[@objtype='typedef']")
        for elem in typedef_xpath.xpath("./desc"):
            typedef_section.append(deepcopy(elem))
        typedef_xpath.find("..").replace(typedef_xpath, typedef_section)

        # Move exceptions to a dedicated section
        exception_section = E.section(id="exception_classes")
        exception_classes = self.root.xpath(
            "./desc[@objtype='class' and desc_signature//desc_name[contains(text(), 'Exception')]]"
        )
        for elem in exception_classes:
            exception_section.append(deepcopy(elem))
            self.root.remove(elem)
        self.root.find("./section[@id='typedefs']").addnext(exception_section)

        # Move structs to a dedicated section
        structs_section = E.section(id="structs")
        structs = self.root.xpath("./desc[@objtype='struct']")
        for elem in structs:
            structs_section.append(deepcopy(elem))
            self.root.remove(elem)
        self.root.find("./section[@id='exception_classes']").addnext(structs_section)

        # Move classes to a dedicated section
        classes_section = E.section(id="classes")
        classes = self.root.xpath("./desc[@objtype='class']")
        for elem in classes:
            classes_section.append(deepcopy(elem))
            self.root.remove(elem)
        self.root.find("./section[@id='structs']").addnext(classes_section)

        ref_xpath = (
            "./section[@id='classes' or @id='exception_classes']"
            "//desc_parameterlist/desc_parameter/reference"
        )
        for elem in self.root.xpath(ref_xpath):
            reftitle = elem.get("reftitle", default=elem.text)
            new_ref = E.desc_type(reftitle)

            new_tail = elem.tail.lstrip()
            if len(new_tail) < len(elem.tail):
                new_tail = f" {new_tail}"
            if len(new_tail := new_tail.rstrip()):
                new_ref.tail = new_tail

            parent = elem.find("..")
            parent.replace(elem, new_ref)

        def add_desc_type(elem, param_type):
            if len(split_type := param_type.split(" ")) > 1:
                param_type = split_type[0]
                param_annotation = split_type[1]
            else:
                param_annotation = ""

            type_elem = E.desc_type(param_type)
            if param_annotation:
                type_elem.tail = f" {param_annotation}"

            return type_elem

        for elem in self.root.xpath(".//desc_parameter[text()!='']"):
            param_type = elem.text.strip()
            if not len(param_type):
                continue

            type_elem = add_desc_type(elem, param_type)

            elem.text = ""
            elem.insert(0, type_elem)

        for elem in self.root.xpath(".//desc_parameter/desc_annotation[position()=1]"):
            param_type = elem.tail.strip()
            if not len(param_type):
                continue

            type_elem = add_desc_type(elem, param_type)

            elem.tail = ""
            elem.addnext(type_elem)

        for elem in self.root.xpath(".//desc_parameterlist/desc_parameter"):
            if elem.find("./*[1]").tag != "desc_annotation":
                elem.insert(0, E.desc_annotation(""))

        for elem in self.root.xpath(".//desc_parameterlist/desc_parameter"):
            type_elem = elem.find("./desc_type")
            if type_elem.tail is None or not len(type_elem.tail):
                desc_ref = E.desc_ref("")
                type_elem.addnext(desc_ref)
                continue

            new_tail = type_elem.tail.strip()
            desc_ref = E.desc_ref(new_tail)

            type_elem.tail = ""
            type_elem.addnext(desc_ref)

        for elem in self.root.xpath(".//desc_parameterlist/desc_parameter"):
            ref_elem = elem.find("./desc_ref")

            if not ref_elem.tail or not len(ref_elem.tail.strip()):
                ref_elem.tail = ""

            old_elem = ref_elem.getnext()
            elem.replace(old_elem, E.desc_name(old_elem.text))
            # print(ref_elem.tail, ref_elem.getnext())

        ref_xpath = ".//desc[@objtype='function']//desc_signature_line/reference"
        for elem in self.root.xpath(ref_xpath):
            prev_elem = elem.getprevious()

            if prev_elem is None:
                prev_elem = E.desc_returns()

            if prev_elem.text is None or not len(prev_elem.text):
                prev_elem.text = elem.text

            if elem.tail:
                ref_tail = elem.tail.strip()
            else:
                ref_tail = ""

            desc_ref = E.desc_ref(ref_tail)
            elem.tail = ""

            parent = elem.find("..")
            parent.replace(elem, desc_ref)


if __name__ == "__main__":
    main()

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


def ugly_dump_if_contains(tree, contains, count=1000):

    if tree is None:
        return

    dumped = etree.tostring(
        tree,
        encoding="utf-8",
        pretty_print=False,
    ).decode("utf-8")

    if dumped.find(contains) > -1:
        print("↓↓↓↓↓↓↓↓↓↓↓")
        print(dumped, end="")
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

        self.pre_tidy_tree()

        # return
        if self.domain == self.DOMAIN_CPP:
            self._parse_cpp()
        elif self.domain == self.DOMAIN_PY:
            self._parse_py()

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

    def pre_tidy_tree(self):
        for elem in self.root.xpath(".//desc_signature"):
            ids = elem.get("ids")
            if ids:
                new_id = ids.split(" ")[-1]
                new_id = new_id.strip()

                elem.set("ids", new_id)

        terms_xpath = "//term[count(./*)<2 and ./strong]"
        for elem in self.root.xpath(terms_xpath):
            etree.strip_tags(elem, "strong")
            elem.text = elem.text.strip()

        for elem in self.root.xpath(".//index"):
            parent = elem.find("..")
            parent.remove(elem)

        for elem in self.root.xpath(".//desc_signature_line"):
            parent = elem.find("..")
            parent.extend(list(deepcopy(elem)))
            parent.remove(elem)

    def tidy_tree(self):

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

        for elem in self.root.xpath("//paragraph"):
            if not elem.text or len(elem.text.strip()) == 0:
                if not elem.tail or len(elem.tail.strip()) == 0:
                    if len(list(elem)) == 0:
                        elem.find("..").remove(elem)
                continue

            if len(elem) and elem.text[-1] == " ":
                continue

            elem.text = elem.text.strip()

            if len(elem.text) == 0:
                continue

            final_char = elem.text[-1]
            if final_char in "\"'":
                final_char = elem.text[-1]

            if final_char not in "!.?:,":
                elem.text = f"{elem.text}."

    def _parse_py(self):
        if self.domain != self.DOMAIN_PY:
            raise RuntimeError("_parse_py can only be called on Python definitions.")

        # Move classes to a dedicated section
        classes_section = self.__arrange_classes()
        self.root.find("./section[@id='abstract']").addnext(classes_section)

        # This function isn't likely to do anything to Python docs,
        # but it can't hurt.
        self.__remove_reference_elems()

        # Rename field and remove unnecessary attr
        sig_names = self.root.xpath(".//desc_parameter/desc_sig_name")
        for sig_name in sig_names:
            parent = sig_name.find("..")

            new_name = E.desc_name(sig_name.text.strip())
            parent.replace(sig_name, new_name)

            if (next_elem := new_name.getnext()) is not None:
                if next_elem.tag == "desc_sig_operator":
                    parent.remove(next_elem)

        # Rename default values field
        default_value_elems = self.root.xpath(
            ".//desc_parameter/inline[@classes='default_value']"
        )
        for elem in default_value_elems:
            parent = elem.find("..")

            new_elem = E.default_value(elem.text.strip())
            parent.replace(elem, new_elem)

        self.__clean_classes()

    def __rename_python_param_elems(self):
        methods = self.root.xpath(".//desc[@objtype='method']")

        for method in methods:
            content = method.find("./desc_content")
            # ugly_dump(content)

            field_list = content.find("./field_list")
            if field_list is None:
                continue

            definition_list = E.definition_list("")
            for elem in field_list:
                definition_list.append(deepcopy(elem))
            content.replace(field_list, definition_list)

    def _parse_cpp(self):
        if self.domain != self.DOMAIN_CPP:
            raise RuntimeError("_parse_cpp can only be called on C++ definitions.")

        # Remove the namespace wrapper
        namespace_wrappers = self.root.xpath("./desc[@desctype='type']")
        for wrapper in namespace_wrappers:
            namespace_contents = wrapper.xpath(
                "./desc_signature[./target[contains(@ids, 'namespace')]]"
                "/following-sibling::desc_content[1]/*"
            )

            ix = self.root.index(wrapper)
            for elem in namespace_contents:
                self.root.insert(ix, deepcopy(elem))
                ix += 1

            self.root.remove(wrapper)

        for elem in self.root.xpath(".//desc_signature/target"):
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

        # # Move classes to a dedicated section
        # classes_section = E.section(id="classes")
        # classes = self.root.xpath("./desc[@objtype='class']")
        # for elem in classes:
        #     classes_section.append(deepcopy(elem))
        #     self.root.remove(elem)
        classes_section = self.__arrange_classes()
        self.root.find("./section[@id='structs']").addnext(classes_section)

        # ref_xpath = (
        #     "./section[@id='classes' or @id='exception_classes']"
        #     "//desc_parameterlist/desc_parameter/reference"
        # )
        # for elem in self.root.xpath(ref_xpath):
        #     reftitle = elem.get("reftitle", default=elem.text)
        #     new_ref = E.desc_type(reftitle)

        #     new_tail = elem.tail.lstrip()
        #     if len(new_tail) < len(elem.tail):
        #         new_tail = f" {new_tail}"
        #     if len(new_tail := new_tail.rstrip()):
        #         new_ref.tail = new_tail

        #     parent = elem.find("..")
        #     parent.replace(elem, new_ref)
        self.__remove_reference_elems()

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

        ref_xpath = ".//desc[@objtype='function']//desc_signature/reference"
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

        source_file_name_elems = self.root.xpath(
            ".//desc_content/*[1][name()='emphasis']"
        )
        for elem in source_file_name_elems:
            if elem.text is None:
                continue

            if elem.text.strip().startswith("#include"):
                source_file_name = elem.text.strip()
                source_file_name = source_file_name.removeprefix("#include")
                source_file_name = source_file_name.replace("&lt;", "")
                source_file_name = source_file_name.replace("&gt;", "")

                elem.find("..").replace(
                    elem, E.source_file(source_file_name.strip("<> "))
                )

        function_sigs = self.root.xpath(
            ".//desc[@objtype='function']//desc_signature/desc_returns"
        )
        for desc_return in function_sigs:
            if desc_return.getnext().tag != "desc_ref":
                desc_return.addnext(E.desc_ref(""))

        self.__clean_typedefs()
        self.__clean_classes()

    def __arrange_classes(self):
        # Move classes to a dedicated section
        classes_section = E.section(id="classes")
        classes = self.root.xpath("./desc[@objtype='class']")
        for elem in classes:
            classes_section.append(deepcopy(elem))
            self.root.remove(elem)

        return classes_section

    def __remove_reference_elems(self):
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

    def __clean_classes(self):
        exception_classes = self.root.xpath(
            ".//section[@id='exception_classes' or @id='classes']/desc"
        )
        for obj in exception_classes:
            self.__clean_class_signature(obj.xpath("desc_signature"))

            self.__clean_class_content(obj.xpath("desc_content"))

    def __clean_class_content(self, elem_root):
        if type(elem_root) is list:
            for elem in elem_root:
                self.__clean_class_content(elem)
            return

        # Extract functions from section containers
        section_containers = elem_root.xpath(
            "./container[contains(@classes, 'breathe-sectiondef')]"
        )
        for section in section_containers:
            rubric = section.find("./*[1][@classes='breathe-sectiondef-title']")
            if rubric is None:
                continue

            section_name = rubric.text.strip()
            section.remove(rubric)

            section_index = elem_root.index(section)

            functions = section.xpath("./desc[@objtype='function']")
            for func in functions:
                func.set("section-name", section_name)

                elem_root.insert(section_index, deepcopy(func))
                section_index += 1

            elem_root.remove(section)

        self.__clean_function(
            elem_root.xpath(".//desc[@objtype='function' or @objtype='method']")
        )

    def __clean_function(self, elem_root):
        if type(elem_root) is list:
            for elem in elem_root:
                self.__clean_function(elem)
            return

        content = elem_root.find("./desc_content")

        # Correct a weird issue apparently introduced by Sphinx or Breathe,
        # where the entire definition list somehow gets embedded in a paragraph.
        def_list = content.find("./paragraph/definition_list")
        if def_list:
            new_def_list = content.append(deepcopy(def_list))
            def_list.find("..").remove(def_list)

        # Extract bullet lists that are nested within paragraphs
        nested_bullets = content.xpath(".//paragraph/bullet_list")
        for nested in nested_bullets:
            parent = nested.find("..")
            parent.addnext(deepcopy(nested))
            parent.remove(nested)

        if self.domain == self.DOMAIN_CPP:
            function_description = content.xpath(
                "./definition_list/preceding-sibling::*"
            )
        else:
            function_description = content.xpath("./field_list/preceding-sibling::*")
            # ugly_dump(content)
            # if (_ := content.find("./field_list")) :
            #     ugly_dump(_)

        desc = E.func_description("")
        for elem in function_description:
            new_elem = deepcopy(elem)
            # ugly_dump(new_elem)

            if new_elem.text:
                new_elem.text = new_elem.text.strip()
            else:
                new_elem.text = ""

            desc.append(new_elem)
            content.remove(elem)
        content.insert(0, desc)

        # self.__rename_python_param_elems()

        if self.domain == self.DOMAIN_CPP:
            def_list = content.find("./definition_list")
        else:
            def_list = content.find("./field_list")

        if def_list is None:
            def_items = []
        else:
            if self.domain == self.DOMAIN_CPP:
                def_items = def_list.xpath("./definition_list_item")
            else:
                def_items = def_list.xpath("./field")

        for item in def_items:
            if self.domain == self.DOMAIN_CPP:
                term = item.find("./term")
            else:
                term = item.find("./field_name")

            if term.text in ("Parameters", "Exceptions", "Raises"):
                if self.domain == self.DOMAIN_CPP:
                    sub_items = item.xpath("./definition/bullet_list/list_item")
                else:
                    sub_items = item.xpath("./field_body/bullet_list/list_item")
                    if len(sub_items) == 0:
                        sub_items = item.xpath("./field_body")
                if sub_items is None:
                    continue

                new_list = E.definition_list("")
                content_type_term = term.text.lower()
                if content_type_term == "raises":
                    content_type_term = "exceptions"
                new_list.set("content-type", content_type_term)
                for _ in sub_items:
                    # if content_type_term == "exceptions":
                    #     ugly_dump(_)
                    new_list.append(deepcopy(_))

                if content_type_term == "parameters":
                    content.insert(1, new_list)
                else:
                    content.append(new_list)

                item.find("..").remove(item)
            elif term.text == "Return":
                new_item = E.return_value("")

                if self.domain == self.DOMAIN_CPP:
                    val = item.find("./definition")
                else:
                    val = item.find("./field_body")

                new_item.extend(deepcopy(val).getchildren())

                content.append(new_item)
                item.find("..").remove(item)

        if def_list is not None:
            content.remove(def_list)

        if self.domain == self.DOMAIN_PY:
            literal_emph = content.xpath(
                ".//definition_list//list_item//literal_emphasis"
            )

            for elem in literal_emph:
                elem.tag = "literal"
                elem.set("classes", "xref")

        param_list = content.find("./definition_list[@content-type='parameters']")
        param = None
        if param_list is not None:
            for param in param_list:
                new_item = E.param("")

                param_values = list(param)
                if self.domain == self.DOMAIN_CPP:
                    param_line = param_values[0].find("./literal")
                    param_name = param_line.text
                    param_desc = param_line.tail

                    if param_name:
                        param_name_elem = E.param_name(param_name.strip())
                    else:
                        param_name_elem = E.param_name("")

                    new_item.append(param_name_elem)

                    if param_desc:
                        param_desc = param_desc.lstrip(":")
                        param_desc_elem = E.param_desc(E.paragraph(param_desc.strip()))
                    else:
                        param_desc_elem = E.param_desc("")

                    if len(param_values) > 1:
                        param_desc_elem.extend(param_values[1:])

                else:
                    new_item = self.__process_python_methods(
                        new_item,
                        param_values[0],
                        param_values[1:],
                    )

                param_list.replace(param, deepcopy(new_item))

        exceptions_list = content.find("./definition_list[@content-type='exceptions']")
        # if exceptions_list:
        #     ugly_dump(exceptions_list)
        if exceptions_list is not None:
            for exc in exceptions_list:
                new_item = E.exception("")

                exc_values = list(exc)
                exc_line = None
                if self.domain == self.DOMAIN_CPP:
                    exc_line = exc_values[0].find("./literal")
                    exc_name = exc_line.text.strip()
                    exc_desc = exc_line.tail
                else:
                    exc_line = exc_values[0].xpath(
                        "./*[starts-with(name(), 'literal')]"
                    )[0]
                    exc_name = exc_line.text.strip()

                    if exc_line.tail:
                        exc_desc = exc_line.tail.lstrip(" –")

                if exc_line is not None:
                    exc_line.find("..").remove(exc_line)

                exc_name_elem = E.exception_name(exc_name)
                new_item.append(exc_name_elem)

                if exc_desc:
                    exc_desc = exc_desc.lstrip(":")
                    exc_desc_elem = E.exception_desc(exc_desc.strip())
                else:
                    exc_desc_elem = E.exception_desc("")

                if len(exc_values[0]):
                    for _ in exc_values[0]:
                        exc_desc_elem.append(deepcopy(_))
                        _.find("..").remove(_)

                if len(exc_values) > 1:
                    exc_desc_elem.extend(exc_values[1:])

                new_item.append(exc_desc_elem)

                exceptions_list.replace(exc, new_item)

        return_value_elem = content.find("./return_value")
        if return_value_elem is not None:
            content.append(deepcopy(return_value_elem))
            content.remove(return_value_elem)

    def __process_python_methods(self, new_item, param_elems, tail_elems: list = None):
        children = param_elems.iterchildren()
        first_child = next(children)

        param_name_elem = E.param_name("")
        param_name_elem.text = first_child.text.strip()

        new_item.append(param_name_elem)

        param_type_elem = E.param_type("")
        param_desc_elem = E.param_desc("")

        if not first_child.tail:
            print("NO TAIL!:")
            ugly_dump(param_elems)
        else:
            first_elem_tail = first_child.tail
            param_elems.remove(first_child)

        # If it has no type at all, we just add the empty param_type
        # element to the tree and add the tail of the parameter name
        # element's tail.
        if first_elem_tail != " (":
            new_item.append(param_type_elem)

            param_description = first_elem_tail.lstrip(" –")
            param_description = param_description.strip()

            fixed_newlines = []
            for line in param_description.split("\n"):
                fixed_newlines.append(line.strip())

            param_desc_elem.text = " ".join(fixed_newlines)

            while (next_elem := next(children, None)) is not None:
                param_desc_elem.append(deepcopy(next_elem))
                next_elem.find("..").remove(next_elem)

        # If the tail is " (", then it means that a type is specified.
        # We have to consider a few things about how we process this.
        else:

            type_literals = param_elems.xpath("./literal[contains(@classes, 'xref')]")

            if len(type_literals) == 1:
                param_type_elem.text = type_literals[0].text.strip()

                if type_literals[0].tail:
                    param_desc_elem.text = type_literals[0].tail

                param_desc_elem.text = param_desc_elem.text.lstrip(")")
                param_desc_elem.text = param_desc_elem.text.strip(" –")
                param_desc_elem.text = param_desc_elem.text.strip()

                param_elems.remove(type_literals[0])

            else:
                type_text = []
                for _ in type_literals:
                    if _.text:
                        type_text.append(_.text)
                    if _.tail:
                        type_text.append(_.tail)

                    param_elems.remove(_)

                selected_type_text = "".join(type_text)
                segments = selected_type_text.split(" – ")
                selected_type_text = segments[0]
                selected_type_text = selected_type_text.rstrip(" )")
                param_type_elem.text = selected_type_text

                if len(segments) > 1:
                    end_segment = " – ".join(segments[1:])

                    param_desc_elem.text = end_segment.lstrip(")")
                    param_desc_elem.text = param_desc_elem.text.strip(" –")
                    param_desc_elem.text = param_desc_elem.text.strip()

            remaining_elems = list(param_elems)
            for _ in remaining_elems:
                param_desc_elem.append(deepcopy(_))
                param_elems.remove(_)

        if tail_elems:
            for _ in tail_elems:
                param_desc_elem.append(deepcopy(_))
                _.find("..").remove(_)

        if param_type_elem is not None:
            new_item.append(param_type_elem)
        if param_desc_elem is not None:
            new_item.append(param_desc_elem)

        return new_item

    def __clean_class_signature(self, elem_root):
        if type(elem_root) is list:
            for elem in elem_root:
                self.__clean_class_signature(elem)
            return

        self.__remove_unneeded_returns(elem_root)
        self.__fix_elem_spacing(elem_root, ["desc_annotation"])

        parent_class = []
        if (name_elem := elem_root.find("./desc_name")) is not None:
            if name_elem.tail and len(name_elem.tail.strip()):
                if name_elem.tail.strip() != ":":
                    tail = name_elem.tail.strip()
                    parent_class = [E.unknown(tail)]

            name_elem.tail = ""

            parent_class.append(name_elem.getnext())
            while parent_class[-1] is not None:
                parent_class.append(parent_class[-1].getnext())
            del parent_class[-1]

            if parent_class and parent_class[0].tag == "desc_annotation":
                new_parent = E.parent_annotation(parent_class[0].text.strip())
                parent_name = E.parent_name(parent_class[0].tail.strip())

                elem_root.replace(parent_class[0], new_parent)
                new_parent.addnext(parent_name)

    def __clean_typedefs(self):
        typedefs = self.root.xpath(".//section[@id='typedefs']/desc")
        for obj in typedefs:
            self.__clean_typedef_signature(obj.xpath("desc_signature"))

    def __clean_typedef_signature(self, elem_root):
        if type(elem_root) is list:
            for elem in elem_root:
                self.__clean_typedef_signature(elem)
            return

        self.__remove_unneeded_returns(elem_root)
        self.__fix_elem_spacing(elem_root, "desc_annotation")

        for elem in elem_root.xpath(".//desc_annotation"):
            if elem.tail:
                desc_type = E.desc_type(elem.tail.strip())
                elem.tail = ""

                elem.addnext(desc_type)
            else:
                elem.addnext(E.desc_type(""))

    def __remove_unneeded_returns(self, elem_root):
        # Remove `returns` statement from typedef signatures
        for elem in elem_root.xpath(".//desc_returns"):
            elem_root.remove(elem)

    def __fix_elem_spacing(self, elem_root, tags):
        if type(tags) is list:
            for tag in tags:
                self.__fix_elem_spacing(elem_root, tag)
            return

        tag = f".//{tags}"
        for elem in elem_root.xpath(tag):
            if elem.text:
                elem.text = elem.text.strip()


if __name__ == "__main__":
    main()

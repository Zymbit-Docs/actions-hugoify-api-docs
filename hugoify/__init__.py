# from .markdownify import main
import os, sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from lxml import etree
from lxml.builder import E

from .utils import generate_frontmatter
from .utils import partial_dump, ugly_dump, ugly_dump_if_contains

from pprint import pprint

# from .xslt import xslt
from .htmlify import htmlify


def main():
    input_dir = Path(os.getenv("INPUT_RAWPATH", "content/GENERATED/"))
    output_dir = Path(os.getenv("INPUT_OUTPUTPATH", "content/api/"))

    if not input_dir.exists():
        print("Exiting because there are no files to process...")
        print(f"{input_dir.resolve()} does not exist!")
        sys.exit(0)

    print(f"Processing content of {input_dir.resolve()}...")
    print(f"Outputting results to {output_dir.resolve()}...")

    for f in input_dir.glob("*_api.xml"):
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

        output_xml = input_dir / f"{f.stem}-processed.xml"

        with output_xml.open("w") as fp:
            doc = E.document()

            if contents.domain == CodeFile.DOMAIN_PY:
                doc.set("api-lang", "python")
                doc.set("title", "Python API Documentation")
            elif contents.domain == CodeFile.DOMAIN_CPP:
                doc.set("api-lang", "cpp")
                doc.set("title", "C++ API Documentation")
            elif contents.domain == CodeFile.DOMAIN_C:
                doc.set("api-lang", "c")
                doc.set("title", "C API Documentation")

            title_element = E.document_title(doc.get("title"))
            doc.append(title_element)

            children = root.find("./section").getchildren()
            doc.extend(children)
            etree.indent(doc, space="    ", level=1)
            doc_text = etree.tostring(doc, encoding="unicode")
            fp.write(doc_text)
            fp.write("\n")

        print()

    htmlify(input_dir, output_dir)

    sys.exit(0)


def extract_text(elem):
    return str(elem.text).lstrip()


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
        if self.domain == self.DOMAIN_C:
            self._parse_c()
        elif self.domain == self.DOMAIN_CPP:
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

        for elem in self.root.xpath(
            ".//desc[@objtype='method']/desc_content/field_list/field[./field_name[text()='Parameters']]/field_body"
        ):
            if p := elem.xpath("./paragraph"):
                if len(p) != 1:
                    raise RuntimeError("Unknown parsing condition!")

                new_elem = E.bullet_list(E.list_item(deepcopy(p[0])))
                # new_elem.append(deepcopy(p[0]))

                elem.remove(p[0])

                elem.append(new_elem)

                # ugly_dump(elem)

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
            if len(elem) == 1:
                only_child = elem.find("./*")

                if only_child.text or len(only_child):
                    if only_child.tail and not only_child.tail.isspace():
                        continue
            elif len(elem) > 1:
                for child in elem.xpath("./*"):
                    if child.tag not in {"strong", "title_reference"}:
                        break
                else:
                    continue

                # print("Not skipping for:")
                # ugly_dump(elem)

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

        for elem in self.root.xpath("//title_reference"):
            if (prev_sibling := elem.getprevious()) is not None:
                if not prev_sibling.tail:
                    prev_sibling.tail = " "
                else:
                    prev_sibling.tail += " "
            else:
                parent = elem.getparent()
                if not parent.text:
                    parent.text = " "
                else:
                    parent.text += " "

    def _parse_c(self):
        if self.domain != self.DOMAIN_C:
            raise RuntimeError("_parse_c can only be called on Python definitions.")

        # Correct the domain
        bad_domain_elems = self.root.xpath("//*[@domain='cpp' or @classes='cpp']")
        for elem in bad_domain_elems:
            if elem.get("domain", None) == "cpp":
                elem.set("domain", "c")
            if (elem_classes := elem.get("classes", "")).find("cpp") > -1:
                elem.set("classes", elem_classes.replace("cpp", "c"))

        for elem in self.root.xpath(".//desc_signature/target"):
            if not elem.tail:
                continue

            return_elem = E.desc_returns(elem.tail.strip())
            parent = elem.find("..")
            parent.replace(elem, return_elem)

        # Move typedefs to a dedicated section
        # typedef_section = E.section(id="typedefs")
        # typedef_xpath = self.root.find("./container[@objtype='typedef']")
        # for elem in typedef_xpath.xpath("./desc"):
        #     typedef_section.append(deepcopy(elem))
        # typedef_xpath.find("..").replace(typedef_xpath, typedef_section)

        # Move defines to a dedicated section
        defines_section = E.section(id="defines")
        defines = self.root.xpath(".//desc[@objtype='macro']")
        for elem in defines:
            defines_section.append(deepcopy(elem))
            elem.getparent().remove(elem)
        if (typedef_section := self.root.find("./section[@id='typedefs']")) is not None:
            typedef_section.addprevious(defines_section)
        else:
            self.root.append(defines_section)

        if (
            defines_container := self.root.find("./container[@objtype='define']")
        ) is not None:
            defines_container.getparent().remove(defines_container)

        # Move structs to a dedicated section
        structs_section = E.section(id="structs")
        structs = self.root.xpath(".//desc[@objtype='struct']")
        for elem in structs:
            structs_section.append(deepcopy(self.__clean_struct(elem)))
            elem.getparent().remove(elem)
        if (typedef_section := self.root.find("./section[@id='typedefs']")) is not None:
            typedef_section.addnext(structs_section)
        else:
            self.root.append(structs_section)

        # Move enums to a dedicated section
        enums_section = E.section(id="enums")
        enums = self.root.xpath(".//desc[@objtype='enum']")
        for elem in enums:
            enums_section.append(deepcopy(elem))
            elem.getparent().remove(elem)
        if (structs_section := self.root.find("./section[@id='structs']")) is not None:
            structs_section.addnext(enums_section)
        else:
            self.root.append(enums_section)

        if (
            enum_container := self.root.find("./container[@objtype='enum']")
        ) is not None:
            enum_container.getparent().remove(enum_container)

        # Add contexts to individual functions, then move the functions to the top level
        functions_section = E.section(id="functions")
        func_containers = self.root.xpath(
            "./container[@objtype='user-defined' and ./desc[@objtype='function']]"
        )

        contexts_list = {"": E.func_context("")}
        for container in func_containers:
            container_context_elem = container.find("./rubric")
            if container_context_elem is not None:
                container_context = container_context_elem.text
            else:
                container_context = ""

            if (parent_context := contexts_list.get(container_context, None)) is None:
                contexts_list[container_context] = E.func_context("")
                contexts_list[container_context].append(
                    E.desc_context(container_context)
                )

            for func in container.xpath("./desc[@objtype='function']"):
                # func.insert(0, E.desc_context(container_context))
                # func.set("context", container_context)
                contexts_list[container_context].append(deepcopy(func))

            container.getparent().remove(container)

        functions_section.extend([_ for _ in contexts_list.values() if len(_) > 0])

        if (enums_section := self.root.find("./section[@id='enums']")) is not None:
            enums_section.addnext(functions_section)
        else:
            self.root.append(functions_section)

        # Add contexts to individual attribs, then move the attribs to the top level
        # functions_section = E.section(id="functions")
        # func_containers = self.root.xpath(
        #     "./desc[@objtype='struct']//container[@objtype='public-attrib']"
        # )

        # Remove the namespace wrapper
        # namespace_wrappers = self.root.xpath("./desc[@desctype='type']")
        # for wrapper in namespace_wrappers:
        #     namespace_contents = wrapper.xpath(
        #         "./desc_signature[./target[contains(@ids, 'namespace')]]"
        #         "/following-sibling::desc_content[1]/*"
        #     )

        #     ix = self.root.index(wrapper)
        #     for elem in namespace_contents:
        #         self.root.insert(ix, deepcopy(elem))
        #         ix += 1

        #     self.root.remove(wrapper)

        self._parse_cpp()
        self.__clean_function(self.root.xpath(".//desc[@objtype='function']"))
        self.__clean_enum(self.root.xpath(".//desc[@objtype='enum']"))
        self.__remove_reference_elems()

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
        self.__remove_unneeded_attrs()
        self.unnest_xpath(".//return_value", "./paragraph")

    def unnest_xpath(self, outer_xpath, inner_xpath):
        outer_elems = self.root.xpath(outer_xpath)
        for outer_elem in outer_elems:
            original_copy = deepcopy(outer_elem)
            if outer_elem.text:
                outer_text = [outer_elem.text]
            else:
                outer_text = []

            inner_elems = outer_elem.xpath(inner_xpath)
            for elem in inner_elems:
                if elem.text:
                    outer_text.append(elem.text)
                    elem.text = ""

            outer_elem.text = "".join(outer_text)

            # outer_elem.addnext(original_copy)

    def __remove_unneeded_attrs(self):
        attrs = self.root.xpath(
            ".//desc["
            "@domain='py' and "
            "@objtype='attribute' and "
            "./desc_signature/desc_name["
            "text()='__dict__' or text()='__weakref__' or text()='__module__'"
            "]]"
        )

        for attr in attrs:
            attr.find("..").remove(attr)

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
        # if self.domain != self.DOMAIN_CPP:
        #     raise RuntimeError("_parse_cpp can only be called on C++ definitions.")

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
            if not elem.tail:
                continue

            elem.tail = elem.tail.strip()
            return_elem = E.desc_returns(elem.tail)
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
            # structs_section.append(deepcopy(elem))
            structs_section.append(deepcopy(self.__clean_struct(elem)))
            self.root.remove(elem)
        self.root.find("./section[@id='exception_classes']").addnext(structs_section)

        # # Move classes to a dedicated section
        # classes_section = E.section(id="classes")
        # classes = self.root.xpath("./desc[@objtype='class']")
        # for elem in classes:
        #     classes_section.append(deepcopy(elem))
        #     self.root.remove(elem)
        if self.domain != self.DOMAIN_C:
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
            if not elem.text or not len(elem.text):
                continue

            param_type = elem.text.strip()

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
            if type_elem is None:
                continue
            if type_elem.tail is None or not type_elem.tail:
                desc_ref = E.desc_ref("")
                type_elem.addnext(desc_ref)
                continue

            new_tail = type_elem.tail.strip()
            desc_ref = E.desc_ref(new_tail)

            type_elem.tail = ""
            type_elem.addnext(desc_ref)

        for elem in self.root.xpath(".//desc_parameterlist/desc_parameter"):
            ref_elem = elem.find("./desc_ref")

            if ref_elem is None:
                continue
            if not ref_elem.tail or not len(ref_elem.tail.strip()):
                ref_elem.tail = ""

            old_elem = ref_elem.getnext()
            default_val = deepcopy(old_elem)
            elem.replace(old_elem, E.desc_name(old_elem.text))

            if default_val.tail and len(default_val.tail):
                split_val = default_val.tail.split("=")
                if len(split_val) > 1:
                    val = E.default_value(split_val[1].strip())
                    ref_elem.getparent().append(val)

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

        if self.domain == self.DOMAIN_C:
            ref_xpath = "./section[@id='functions' or @id='typedefs']" "//reference"
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

        # Add contexts to individual functions, then move the functions to the top level
        # functions_section = E.div(id="functions")
        func_containers = elem_root.xpath(
            "./container[(@objtype='user-defined' or @objtype='public-func' or @objtype='private-attrib') and ./desc[@objtype='function' or @objtype='var']]"
        )

        contexts_list = {"": E.func_context("")}
        for container in func_containers:
            container_context_elem = container.find("./rubric")
            if container_context_elem is not None:
                container_context = container_context_elem.text
            else:
                container_context = ""

            if (parent_context := contexts_list.get(container_context, None)) is None:
                contexts_list[container_context] = E.func_context("")
                contexts_list[container_context].append(
                    E.desc_context(container_context)
                )

            for func in container.xpath(
                "./desc[@objtype='function' or @objtype='var']"
            ):
                # func.insert(0, E.desc_context(container_context))
                # func.set("context", container_context)
                contexts_list[container_context].append(deepcopy(func))

            container.getparent().remove(container)

        elem_root.extend([_ for _ in contexts_list.values() if len(_) > 0])

        # for elem in elem_root.xpath("./container[@objtype='private-attrib']"):
        #     for var in elem.xpath("./desc[@objtype='var']"):
        #         content.append(var)

        #     content.remove(elem)

        # if (enums_section := self.root.find("./section[@id='enums']")) is not None:
        #     enums_section.addnext(functions_section)
        # else:
        #     self.root.append(functions_section)

        # Extract functions from section containers
        # section_containers = elem_root.xpath(
        #     "./container[contains(@classes, 'breathe-sectiondef')]"
        # )
        # for section in section_containers:
        #     rubric = section.find("./*[1][@classes='breathe-sectiondef-title']")
        #     if rubric is None:
        #         continue

        #     section_name = rubric.text.strip()
        #     section.remove(rubric)

        #     section_index = elem_root.index(section)

        #     functions = section.xpath("./desc[@objtype='function']")
        #     for func in functions:
        #         func.set("section-name", section_name)

        #         elem_root.insert(section_index, deepcopy(func))
        #         section_index += 1

        #     elem_root.remove(section)

        self.__clean_function(
            elem_root.xpath(".//desc[@objtype='function' or @objtype='method']")
        )

    def debugging(self, elem_root):
        if self.domain == self.DOMAIN_PY:
            text_xml = "test_file3.xml"

            if not self.WRITE_VAR:
                w = "w"
                self.WRITE_VAR = True
            else:
                w = "a"
            with open(text_xml, w) as fp:
                doc = E.document()

                if self.domain == self.DOMAIN_PY:
                    doc.set("api-lang", "python")
                    doc.set("title", "Python API Documentation")

                title_element = E.document_title(doc.get("title"))
                doc.append(title_element)

                doc.extend(deepcopy(elem_root))
                etree.indent(doc, space="    ", level=0)
                fp.write(etree.tostring(doc, encoding="unicode"))
                fp.write("\n")

    def __clean_enum(self, elem_root):
        if type(elem_root) is list:
            for elem in elem_root:
                self.__clean_enum(elem)
            return

        content = elem_root.find("./desc_content")

        enum_description = content.xpath(
            "./desc[@objtype='enumerator'][1]/preceding-sibling::*"
        )

        desc = E.enum_description("")
        for elem in enum_description:
            new_elem = deepcopy(elem)
            # ugly_dump(new_elem)

            if new_elem.text:
                new_elem.text = new_elem.text.strip()
            else:
                new_elem.text = ""

            desc.append(new_elem)
            content.remove(elem)
        content.insert(0, desc)

        for elem in content.xpath("./desc[@objtype='enumerator']"):
            sub_content = elem.find("./desc_content")
            if len(sub_content):
                continue
            if sub_content.text and len(sub_content.text.strip()):
                continue

            elem.remove(sub_content)

            sig = elem.find("./desc_signature")
            if len(sig):
                sig.set("sig-type", "enumerator")

    def __clean_struct(self, elem_root):
        if type(elem_root) is list:
            for elem in elem_root:
                self.__clean_struct(elem)
            return

        content = elem_root.find("./desc_content")

        struct_description = content.xpath(
            "./container[@objtype='public-attrib'][1]/preceding-sibling::*"
        )

        desc = E.struct_description("")
        for elem in struct_description:
            new_elem = deepcopy(elem)
            # ugly_dump(new_elem)

            if new_elem.text:
                new_elem.text = new_elem.text.strip()
            else:
                new_elem.text = ""

            desc.append(new_elem)
            content.remove(elem)
        content.insert(0, desc)

        for elem in content.xpath("./container[@objtype='public-attrib']"):
            for var in elem.xpath("./desc[@objtype='var']"):
                content.append(var)

            content.remove(elem)

        return elem_root

    def __clean_function(self, elem_root):
        if type(elem_root) is list:
            for elem in elem_root:
                self.__clean_function(elem)
            return

        self.debugging(elem_root)

        content = elem_root.find("./desc_content")

        # Correct a weird issue apparently introduced by Sphinx or Breathe,
        # where the entire definition list somehow gets embedded in a paragraph.
        def_list = content.xpath("./paragraph/definition_list")
        # if def_list:
        for item in def_list:
            parent = item.find("../..")
            parent.append(deepcopy(item))
            # new_def_list = content.append(deepcopy(def_list))

            item.find("..").remove(item)

        def_list = content.xpath("./bullet_list/list_item/definition_list")
        # if def_list:
        for item in def_list:
            parent = item.find("../../..")
            parent.append(deepcopy(item))
            # new_def_list = content.append(deepcopy(def_list))

            item.find("..").remove(item)

        def_list = content.xpath(
            "./paragraph/bullet_list/list_item/paragraph/definition_list"
        )
        # if def_list:
        for item in def_list:
            content.append(deepcopy(item))
            # new_def_list = content.append(deepcopy(def_list))

            item.find("..").remove(item)

        def_list = content.xpath(
            ".//paragraph/definition_list[../*[1][name()='literal_strong']]"
        )
        for item in def_list:
            item.getprevious().tail += item.find("./definition_list_item/term").text
            item.getparent().extend(
                item.find("./definition_list_item/definition").getchildren()
            )
            # content.append(deepcopy(item))
            item.find("..").remove(item)

        # def_list = content.xpath("./bullet_list/list_item/paragraph/definition_list")
        # # if def_list:
        # for item in def_list:
        #     # parent = item.find("../../../..")
        #     content.append(deepcopy(item))
        #     # new_def_list = content.append(deepcopy(def_list))

        #     item.find("..").remove(item)

        # def_list = content.find("./bullet_list/list_item/paragraph/definition_list")
        # if def_list:
        #     ugly_dump(def_list)
        #     new_def_list = content.append(deepcopy(def_list))
        #     def_list.find("..").remove(def_list)

        # Extract bullet lists that are nested within paragraphs
        nested_bullets = content.xpath(".//paragraph/bullet_list")
        for nested in nested_bullets:
            parent = nested.find("..")
            parent.addnext(deepcopy(nested))
            parent.remove(nested)

        if self.domain == self.DOMAIN_CPP or self.domain == self.DOMAIN_C:
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

        # failing_node = False
        if self.domain == self.DOMAIN_CPP or self.domain == self.DOMAIN_C:
            def_list = content.find("./definition_list")
        else:
            def_list = content.find("./field_list")
            # failing_node = ugly_dump_if_contains(def_list, "ERRORY")

        if def_list is None:
            def_items = []
        else:
            if self.domain == self.DOMAIN_CPP or self.domain == self.DOMAIN_C:
                def_items = def_list.xpath("./definition_list_item")
            else:
                def_items = def_list.xpath("./field")

        for item in def_items:
            if self.domain == self.DOMAIN_CPP or self.domain == self.DOMAIN_C:
                term = item.find("./term")
            else:
                term = item.find("./field_name")

            if term.text in ("Parameters", "Exceptions", "Raises"):
                if self.domain == self.DOMAIN_CPP or self.domain == self.DOMAIN_C:
                    sub_items = item.xpath("./definition/bullet_list/list_item")
                else:
                    sub_items = item.xpath("./field_body/bullet_list/list_item")
                    if len(sub_items) == 0:
                        sub_items = item.xpath("./field_body")
                        # [ugly_dump(_) for _ in sub_items]
                if sub_items is None:
                    continue

                new_list = E.definition_list("")
                content_type_term = term.text.lower()
                if content_type_term == "raises":
                    content_type_term = "exceptions"
                new_list.set("content-type", content_type_term)
                for _ in sub_items:
                    new_list.append(deepcopy(_))

                if content_type_term == "parameters":
                    content.insert(1, new_list)
                else:
                    content.append(new_list)

                item.find("..").remove(item)
            elif term.text == "Return" or term.text == "Returns":
                new_item = E.return_value("")

                if self.domain == self.DOMAIN_CPP or self.domain == self.DOMAIN_C:
                    val = item.find("./definition")
                else:
                    val = item.find("./field_body")

                new_item.extend(deepcopy(val).getchildren())

                # new_item[-1].tail = " And here's some follower text!"

                content.append(new_item)
                item.find("..").remove(item)

            elif term.text == "Return type":
                if self.domain == self.DOMAIN_PY:
                    new_item = E.return_type("")

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
                # ugly_dump(elem)
                elem.tag = "literal"
                elem.set("classes", "xref")

        param_list = content.find("./definition_list[@content-type='parameters']")
        param = None
        if param_list is not None:
            for param in param_list:
                new_item = E.param("")

                param_values = list(param)
                if self.domain == self.DOMAIN_CPP or self.domain == self.DOMAIN_C:
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

                    new_item.append(param_desc_elem)

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
                if self.domain == self.DOMAIN_CPP or self.domain == self.DOMAIN_C:
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

    WRITE_VAR = False

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

#!/usr/bin/env python3
import os, sys
from pathlib import Path
from lxml import html, etree
from lxml.html import builder as E
import re
import io
from datetime import datetime
from copy import deepcopy

from typing import List, Any

# import frontmatter
from ruamel.yaml import YAML
from ruamel.yaml.compat import StringIO

from pprint import pprint


class Frontmatter:
    def __init__(self, **kw):
        self.yaml = YAML()
        self.yaml.explicit_start = True
        self.yaml.width = 4096
        self.yaml.indent(mapping=4, sequence=2, offset=4)

    def dump_metadata(self, data, stream=None, **kw):
        inefficient = False

        if stream is None:
            inefficient = True
            stream = StringIO()

        self.yaml.dump(data, stream, **kw)

        stream.write("---\n")
        if inefficient:
            return stream.getvalue()


frontmatter_generator = Frontmatter(typ="safe")


def main():
    input_dir = Path(os.environ["INPUT_RAWPATH"])
    output_dir = Path(os.environ["INPUT_OUTPUTPATH"])

    print(input_dir)

    if not input_dir.exists():
        print("Exiting because there are no files to process...")
        sys.exit(0)
        return

    output_log = []
    for f in input_dir.iterdir():
        print(f"Processing {str(f)}...")
        frontmatter, parsed = parse_file(f)

        output_html = f.parents[1] / "output" / f"{f.stem}.html"

        with output_html.open("w") as fp:
            fp.write(f"<pre>{frontmatter}</pre>\n\n")
            for elem in parsed:
                if elem.get("class") == "parsed-section":
                    dump_markdown(fp, elem)
                else:
                    etree.indent(elem, space="  ", level=0)
                    fp.write(etree.tostring(elem, encoding="unicode"))
                    fp.write("\n")

        output_md = f.parents[1] / "output" / f"{f.stem}.md"
        with output_md.open("w") as fp:
            fp.write(f"{frontmatter}\n")
            for elem in parsed:
                if elem.get("class") == "parsed-section":
                    dump_markdown(fp, elem)
                else:
                    etree.indent(elem, space="  ", level=0)
                    fp.write(etree.tostring(elem, encoding="unicode"))
                    fp.write("\n")

        print()

    sys.exit(0)


def dump_markdown(fp, root: html.HtmlElement, level: int = 0):
    for elem in root:
        if type(elem) is html.HtmlComment:
            fp.write(etree.tostring(elem, encoding="unicode", pretty_print=True))
            fp.write("\n")
        else:
            etree.indent(elem, space="  ", level=level)
            fp.write(etree.tostring(elem, encoding="unicode", pretty_print=True))


def parse_element(elem: html.HtmlElement):
    if elem.tag == "p":
        return f"{elem.text_content()}\n\n"
    else:
        return etree.tostring(elem, encoding="unicode", pretty_print=True)


def parse_file(fp: Path):
    with fp.open("r") as f:
        html_root = html.parse(f)

    comments = html_root.xpath("//comment()")
    lang = ""
    for c in comments:
        comment = str(c)
        if comment.find("API:") == -1:
            continue

        match = re.fullmatch(
            r"<!--\s*API:\s*(?P<lang>[a-z]+)\s*-->", comment, flags=re.IGNORECASE
        )
        if match:
            lang = match.groupdict()["lang"]
            break

    print(f"Processing as language: {lang}")

    body = html_root.getroot().xpath("//body")[0]

    drop_helper_sections(body)
    drop_unwanted_sections(body)
    reformat_elements(body)
    body = get_doc_body(body)

    revised_tree = E.DIV(id="docs-page")

    frontmatter = generate_frontmatter(body)
    fix_wrapping(body)
    get_preamble(body)
    # revised_tree.append(get_preamble(body))

    if lang == "c":
        parse_c_style(body)
        parse_c(body)
    elif lang == "cpp":
        parse_c_style(body)
        parse_cpp(body)
    elif lang == "py":
        parse_py(body)

    for elem in body:
        revised_tree.append(elem)

    return frontmatter, revised_tree


def parse_subsection(
    body_tree: html.HtmlElement,
    elems_xpath: str,
    drop_xpath: str = None,
):
    elems: html.HtmlElement = []
    for match in body_tree.xpath(elems_xpath):
        elems.append(deepcopy(match))
        match.drop_tree()

    if elems and drop_xpath is not None:
        for drop_elem in body_tree.xpath(drop_xpath):
            drop_elem.drop_tree()

    return elems


def parse_c_style(body_tree: html.HtmlElement):
    # Create an array of typedefs
    typedefs: html.HtmlElement = parse_subsection(
        body_tree,
        ".//div[./p[text()='Typedefs']]/dl",
        ".//div[./p[text()='Typedefs']]",
    )

    # Create an array of enums
    enums: html.HtmlElement = parse_subsection(
        body_tree,
        ".//div[./p[text()='Enums']]/dl",
        ".//div[./p[text()='Enums']]",
    )

    # Create an array of defines
    defines: html.HtmlElement = parse_subsection(
        body_tree,
        ".//div[./p[text()='Defines']]/dl",
        ".//div[./p[text()='Defines']]",
    )

    structs: html.HtmlElement = parse_subsection(
        body_tree,
        "./dl[@class='cpp struct']",
    )


def parse_c(body_tree: html.HtmlElement):
    functions: dict[str, List[html.HtmlElement]] = {}

    contextdiv_xpath = ".//div[./dl[@class='cpp function'] and ./p[contains(@class, 'breathe-sectiondef-title')]]"
    for match in body_tree.xpath(contextdiv_xpath):
        section_name = match.find("./p").text_content()
        if not functions.get(section_name):
            functions[section_name] = []

        functions[section_name] += [
            _ for _ in match.xpath("./dl[@class='cpp function']")
        ]
        match.drop_tree()

    pprint(functions)


def parse_cpp(body_tree: html.HtmlElement):

    # Create an array of exception definitions
    exceptions: html.HtmlElement = parse_subsection(
        body_tree,
        ".//dl[@class='cpp class' and ./dt[contains(text(), 'std::exception')]]",
        ".//div[./p[text()='Defines']]",
    )

    classes: html.HtmlElement = parse_subsection(
        body_tree,
        "./dl[@class='cpp class']",
    )


def parse_py(body_tree: html.HtmlElement):
    classes: html.HtmlElement = parse_subsection(
        body_tree,
        "./dl[@class='py class']",
    )


def get_preamble(body_tree: html.HtmlElement):
    first_dl = body_tree.find("dl")
    intro_tree = first_dl.xpath("preceding-sibling::*")

    preamble_div = E.DIV(E.CLASS("parsed-section"), id="preamble")

    preamble_div.append(etree.Comment("SECTION BEGIN: preamble"))

    if first_dl.find("dt").text_content() == "Author":
        first_dl.drop_tree()

    for elem in intro_tree:
        preamble_div.append(deepcopy(elem))
        elem.drop_tree()
        # if elem.tag == "p":
        # elem_copy = deepcopy(elem)
        # elem.drop_tag()
        # stripped_elem = etree.tostring(elem_copy)
        # preamble_lines.append(elem_copy)

    preamble_div.append(etree.Comment("SECTION END: preamble"))

    # pprint(preamble_div)
    return preamble_div


def fix_wrapping(body_tree: html.HtmlElement):
    for p_elem in body_tree.iterfind(".//p"):
        if not len(p_elem.getchildren()):
            p_content = str(p_elem.text_content()).replace("\n", " ").strip()
            p_elem.text = p_content


def generate_frontmatter(body_content: html.HtmlElement):
    metadata: dict = {
        "title": str,
        "description": str,
        "draft": bool,
        "images": list,
        "type": str,
        "layout": str,
        "weight": int,
        "toc": bool,
    }

    page_title = body_content.find("./h1")
    metadata["title"] = str(page_title.text_content()).strip()
    page_title.drop_tree()

    page_description = body_content.find("./p")
    metadata["description"] = str(page_description.text_content()).strip()
    page_description.drop_tree()

    metadata["lastmod"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")

    metadata.update(
        {
            "draft": False,
            "images": [],
            "type": "docs",
            "layout": "single",
            "weight": 0,
            "toc": True,
        }
    )

    first_p = body_content.find("./p")
    if first_p is not None and not first_p.text_content():
        first_p.drop_tree()

    first_span = body_content.find("./span")
    if first_span is not None and not first_span.text_content():
        first_span.drop_tree()

    return frontmatter_generator.dump_metadata(metadata)


def reformat_elements(body_tree: html.HtmlElement):
    if len(body_tree.xpath(".//dl[contains(@class, 'cpp')]")):
        format_type = "cpp"
    elif len(body_tree.xpath(".//dl[contains(@class, 'py')]")):
        format_type = "py"
    else:
        raise RuntimeError("Could not determine formatting type!")

    class_dts = body_tree.xpath(".//dl[contains(@class, 'class')]/dt")
    for elem in class_dts:
        _reformat_class_dt(elem, format_type)


def _get_class_format(elem: html.HtmlElement):
    parent_dl = elem.iterancestors(tag="dl")


def _reformat_class_dt(elem: html.HtmlElement, format_type: str):
    # def_type = ""
    opener = elem.find("./*[@class='property']")
    def_type = opener.text_content()

    sig_prename = ""
    if len(
        val := opener.xpath("following-sibling::*[contains(@class, 'sig-prename')]")
    ):
        sig_prename = val[0].text_content()
        val[0].drop_tree()

    sig_name = ""
    if len(val := opener.xpath("following-sibling::*[contains(@class, 'sig-name')]")):
        sig_name = val[0].text_content()
        val[0].drop_tree()

    opener.drop_tree()

    sig_end = ""
    if format_type == "cpp":
        sig_end = elem.text_content().strip()

    for sub_elem in elem:
        sub_elem.drop_tree()

    class_sig = f"{def_type.strip()} {sig_name.strip()}"
    elem.set("id", class_sig.replace(" ", "_"))

    if sig_end:
        elem.text = f"{class_sig} {sig_end}"
    else:
        elem.text = class_sig

    print(elem.text)


def drop_helper_sections(body_tree: html.HtmlElement):
    for elem in body_tree:
        for removed_class in ("related", "footer"):
            if removed_class in elem.get("class"):
                elem.drop_tree()


def drop_unwanted_sections(body_tree: html.HtmlElement):
    for elem in body_tree.xpath(".//dl[contains(@class, 'attribute')]"):
        for sub_elem in elem.xpath(".//dt/*[contains(@class, 'sig-name')]"):
            attr_name = sub_elem.text_content()
            if attr_name in ("__dict__", "__module__", "__weakref__"):
                elem.drop_tree()

    for elem in body_tree.xpath(".//span[not(text())]"):
        if len(elem.text_content()) == 0:
            elem.drop_tree()

    for elem in body_tree.xpath(".//dl[@class='cpp type']"):
        elem_dt = elem.find("./dt")
        if elem_dt is not None and elem_dt.text_content().find("namespace") > -1:
            elem_dt.drop_tree()
            for dd in elem.xpath("./dd"):
                dd.drop_tag()

            elem.drop_tag()

    ids_to_drop = [
        "zymkey.Zymkey.EPHEMERAL_KEY_SLOT",
        "zymkey.Zymkey.__del__",
    ]

    for drop_id in ids_to_drop:
        for dl in body_tree.xpath(
            f".//dl[contains(@class, 'py') and ./dt[@id='{drop_id}']]"
        ):
            dl.drop_tree()


def get_doc_body(body_tree: html.HtmlElement):
    content_xpath = (
        "./div[@class='document']"
        "/div[@class='documentwrapper']"
        "/div[@class='body']"
    )
    inner_content = body_tree.find(content_xpath)

    for elem in inner_content:
        if elem.get("class") == "section":
            return elem


if __name__ == "__main__":
    main()

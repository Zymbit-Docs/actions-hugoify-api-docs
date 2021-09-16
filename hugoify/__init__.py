import os
import sys
import tempfile
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from pprint import pprint
import typing as t

from docutils.core import publish_string
from lxml import etree
from lxml.builder import E
from sphinxcontrib.napoleon import Config as NapoleonConfig
from sphinxcontrib.napoleon.docstring import NumpyDocstring as NpDocstring

from . import cleanup
from .exceptions import ParsingError, UnknownStructureError, UnknownTagError
from .utils import (
    generate_frontmatter,
    partial_dump,
    ugly_dump,
    ugly_dump_if_contains,
    pptree,
    strtree,
    get_elem_by_xpath,
)


def main():
    # These default directories are intended to be overridden by environment
    # variables passed by the GitHub Action.
    input_dir = Path(os.getenv("INPUT_RAWPATH", "content/GENERATED/"))
    output_dir = Path(os.getenv("INPUT_OUTPUTPATH", "content/api/"))

    if not input_dir.exists():
        print("Exiting because there are no files to process...")
        print(f"{input_dir.resolve()} does not exist!")
        sys.exit(0)

    print(f"Processing content of {input_dir.resolve()}...")
    print(f"Outputting results to {output_dir.resolve()}...")

    # processing_dir = Path(tempfile.mkdtemp(dir="."))
    processing_dir = Path("./tmp-processing")
    processing_dir.mkdir(exist_ok=True)

    for f in input_dir.glob("*_api.xml"):
        print(f"Processing {str(f)}...")

        # Read in the entire XML tree from the file and make the best effort to
        # build it and get the file's root node.
        tree = etree.parse(str(f), parser=etree.XMLParser(remove_comments=True))
        root_node = tree.getroot()

        output_xml = processing_dir / f"{f.stem}-processed.xml"
        api_lang = (f.stem).split("_")[0]

        detaileddescription_elems = root_node.xpath(".//detaileddescription")
        for detaileddesc_elem in detaileddescription_elems:
            _ = cleanup.strip_verbatim_from_detaileddescription(detaileddesc_elem)
            extracted_verbatim_desc, extracted_verbatim_fields = _

            # Do some checks to ensure we don't have any unknown or unexpected
            # elements in our `detaileddescription` node.
            child_elem_list = list(detaileddesc_elem)
            for child_elem in child_elem_list:
                if child_elem.tag != "para":
                    raise UnknownStructureError(
                        child_elem_list[0],
                        detaileddesc_elem,
                        message="This tag is not a known direct descendant of its parent.",
                    )

            print("-------------------------------------------------------")
            last_element_appended = None
            parameterlist_elems = detaileddesc_elem.xpath(".//parameterlist")
            for elem in parameterlist_elems:
                if elem.get("kind") not in {"param", "exception"}:
                    raise UnknownTagError(
                        elem,
                        detaileddesc_elem,
                        f"The `kind` value of {elem.get('kind')} is unknown.",
                    )

                if last_element_appended is None:
                    detaileddesc_elem.append(elem)
                else:
                    last_element_appended.addnext(elem)
                last_element_appended = elem

            simplesect_elems = detaileddesc_elem.xpath(".//simplesect")
            for simplesect_elem in simplesect_elems:
                simplesect_kind = simplesect_elem.get("kind")
                if simplesect_kind in {"author", "version", "date", "copyright"}:
                    continue
                elif simplesect_kind not in {"note", "return"}:
                    raise UnknownTagError(
                        simplesect_elem,
                        detaileddesc_elem,
                        f"The `kind` value of {simplesect_kind} is unknown.",
                    )

                if simplesect_kind == "note":
                    simplesect_elem.getparent().addnext(simplesect_elem)
                elif simplesect_kind == "return":
                    for ancestor in simplesect_elem.iterancestors(
                        "detaileddescription"
                    ):
                        ancestor.append(simplesect_elem)

                # pptree(simplesect_elem.getparent())

            # description_para_elems = detaileddesc_elem.xpath(
            #     "./para[position()=1] | ./para/preceding-sibling::para"
            # )
            all_intro_paras = []
            for elem in detaileddesc_elem:
                if elem.tag != "para":
                    break

                all_intro_paras.append(elem)

            simplesect_description_elem = E("simplesect", kind="description")
            detaileddesc_elem.insert(0, simplesect_description_elem)
            simplesect_description_elem.extend(all_intro_paras)

            if len(extracted_verbatim_desc) > 0:
                # get_elem_by_xpath(detaileddesc_elem, "./simplesect[@kind='description']")
                simplesect_description_elem.extend(extracted_verbatim_desc)

            for subelem in detaileddesc_elem:
                cleanup.convert_doxygen_pseudohtml_nodes(subelem)

        with output_xml.open("w") as fp:

            etree.indent(root_node, space="    ", level=0)
            doc_text = etree.tostring(root_node, encoding="unicode")
            fp.write(doc_text)
            fp.write("\n")


if __name__ == "__main__":
    main()

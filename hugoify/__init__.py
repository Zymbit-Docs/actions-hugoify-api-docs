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
            cleanup.strip_verbatim_from_detaileddescription(detaileddesc_elem)
            continue

            child_elem_list = list(detaileddesc_elem)
            if len(child_elem_list) > 1:
                raise UnknownStructureError(
                    detaileddesc_elem,
                    message="This tag should have exactly 0 or 1 child elements.",
                )

            if len(child_elem_list) == 1:
                if child_elem_list[0].tag != "para":
                    raise UnknownStructureError(
                        child_elem_list[0],
                        detaileddesc_elem,
                        message="This tag is not a known direct descendant of its parent.",
                    )

            for child_elem in child_elem_list:
                cleanup.process_xml_nodes_to_html(child_elem)

        # cleanup.process_verbatim_fields(root_node)

        with output_xml.open("w") as fp:

            etree.indent(root_node, space="    ", level=0)
            doc_text = etree.tostring(root_node, encoding="unicode")
            fp.write(doc_text)
            fp.write("\n")


if __name__ == "__main__":
    main()

import os, sys
from pathlib import Path
from lxml import etree

from pprint import pprint


def xslt():
    input_dir = Path(os.environ["INPUT_RAWPATH"])
    output_dir = Path(os.environ["INPUT_OUTPUTPATH"])

    if not input_dir.exists():
        print("Exiting because there are no files to process...")
        sys.exit(0)

    for f in input_dir.glob("python_docs.xml"):
        print(f"Processing {str(f)}...")

        tree = etree.parse(
            str(f),
            parser=etree.XMLParser(load_dtd=True, no_network=False, recover=True),
        )
        transform = etree.XSLT(etree.parse("input/python.xslt"))

        result_tree = transform(tree.getroot())

        print(result_tree)

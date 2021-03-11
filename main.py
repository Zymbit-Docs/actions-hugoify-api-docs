#!/usr/bin/env python3
import os, sys
import pathlib
from datetime import datetime

from typing import List

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
    input_dir = pathlib.Path(os.environ["INPUT_RAWPATH"])
    output_dir = pathlib.Path(os.environ["INPUT_OUTPUTPATH"])

    output_log = []
    for f in input_dir.iterdir():
        base_file_name = f.name.removeprefix("GENERATED_")
        output_file = output_dir / base_file_name
        output_file = output_file.resolve()

        output_already_exists = output_file.exists()

        input_file = f.resolve()

        generate_output(input_file, output_file)

        if output_already_exists:
            output_log.append(f"Processed the CHANGED file {input_file.name}.")
        else:
            output_log.append(f"Processed the NEW file {input_file.name}.")

    output_result = "\n- ".join(output_log)
    output_result = f"- {output_result}"

    print(f"The following files were processed:\n\n{output_result}")

    with open(".GHA-LOG", "w") as f:
        f.write(output_result)

    sys.exit(0)


page_edit_warning = """
<!--

################################################################################

WARNING: DO NOT EDIT THIS PAGE MANUALLY!

################################################################################

This template should only be used for automatically-generated API documentation.

DO NOT edit the content of this page manually, as it will be overwritten
the next time the API documentation is automatically updated.

################################################################################

WARNING: DO NOT EDIT THIS PAGE MANUALLY!

################################################################################

//-->\n
"""


def generate_output(input_file: pathlib.Path, output_file: pathlib.Path):
    """Process the contents of the input file and write to the output file.

    Parameters
    ----------
    input_file
        A `Path()` representing the file to be processed.
    output_file
        A `Path()` representing the location where the processed file should be written.
    """
    frontmatter = generate_frontmatter(output_file)
    content = parse_content(input_file)

    # Make sure the parent directories exist before attempting to write
    # to the output file.
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w") as f:
        f.write(frontmatter)
        f.write(page_edit_warning)
        f.write(content)


def generate_frontmatter(output_file: pathlib.Path) -> str:
    """Generate the YAML frontmatter containing metadata for Hugo.

    Parameters
    ----------
    output_file
        A `Path()` representing the location where the processed file should be written.

    Returns
    -------
    str
        A string containing the generate YAML frontmatter.
    """
    doc_language = output_file.stem.split("_")[0].capitalize()

    timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")
    metadata = {
        "title": f"{doc_language} API Documentation",
        "description": f"This is the official documentation for the official zkapputils {doc_language} API library.",
        "date": timestamp,
        "lastmod": timestamp,
        "draft": False,
        "images": [],
        "type": "docs",
        "layout": "single",
        "weight": 0,
        "toc": True,
    }

    return frontmatter_generator.dump_metadata(metadata)


def parse_content(input_file: pathlib.Path) -> str:
    """Parse the document and reformat it as appropriate.

    This function begins by removing the H1 header from the first line of the
    markdown file and the following blank line, if present.

    Next, the file will be parsed line by line, turning hard wraps into soft
    wraps. Additionally, any second-level unordered list items will have their
    bullet set as a dash (`-`) if it is currently an asterisk.

    Finally, periods are stripped from the end of any headings.

    Parameters
    ----------
    input_file : pathlib.Path
        A `Path()` representing the file to be processed.

    Returns
    -------
    str
        A string containing the parsed and reformatted doc contents.
    """
    with input_file.open("r") as f:
        file_content = f.readlines()

    first_pass = []
    last_was_newline = False

    if not file_content[0].startswith("# "):
        first_pass.append(file_content[0])

    if file_content[1] != "\n":
        first_pass.append(file_content[1])

    combined_line: List[str] = []
    for line in file_content[2:]:
        if line == "\n":
            if not last_was_newline:
                # first_pass.append(line)
                first_pass.append(" ".join(combined_line))
                first_pass.append("\n\n")
                combined_line = []

            last_was_newline = True
        else:
            last_was_newline = False

            second_level_ol = "    * "
            if line.startswith(second_level_ol):
                line = line.replace(second_level_ol, "    - ")

            # parsed_content.append(line)
            if not combined_line:
                combined_line.append(line.rstrip())
            else:
                combined_line.append(line.strip())

    second_pass = []
    for line in first_pass:
        if line.startswith("##"):
            if line[-1] == ".":
                line = line[:-1]

        second_pass.append(line)

    return "".join(second_pass)


if __name__ == "__main__":
    main()

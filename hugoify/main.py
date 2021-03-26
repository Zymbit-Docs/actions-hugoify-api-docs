#!/usr/bin/env python3
import os, sys
import pathlib
import re
import io
from datetime import datetime

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
    input_dir = pathlib.Path(os.environ["INPUT_RAWPATH"])
    output_dir = pathlib.Path(os.environ["INPUT_OUTPUTPATH"])

    if not input_dir.exists():
        print("Exiting because there are no files to process...")
        sys.exit(0)
        return

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

    with input_file.open("r") as f:
        first_line = next(f)

    if first_line.startswith("# "):
        if len(segments := first_line.split("{")) > 1:
            first_line = segments[0].strip()

        file_title = first_line.removeprefix("# ")
    else:
        file_title = None

    frontmatter = generate_frontmatter(output_file, file_title=file_title)
    content = parse_content(input_file)

    # Make sure the parent directories exist before attempting to write
    # to the output file.
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w") as f:
        f.write(frontmatter)
        f.write(page_edit_warning)
        f.write(content)


def generate_frontmatter(output_file: pathlib.Path, file_title: str = None) -> str:
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
    if doc_language == "cpp":
        doc_language = "C++"

    if not file_title:
        file_title = f"{doc_language} API Documentation"

    timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S%z")
    metadata = {
        "title": file_title.strip(),
        "description": f"This is the official documentation for the official zkapputils {doc_language} API library.",
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
        file_content_str = f.read()

    bolded_item = r"\*{2}(?P<heading>[a-z ]+)\*{2}"
    section = (
        rf"^\* {bolded_item}\n+"
        # rf"[ ]{{4}}(?P<list_heading>\* \*\*[a-z0-9_]+\*\* .+\n\n)"
        rf"(?P<section_body>(([ ]{{2,4}})+.+\n\n*)+)"
    )

    subsection = (
        rf"[ ]{{4}}\* \*\*(?P<list_item_name>.*)\*\* (?P<list_item_body>.*)\n"
        rf"(?P<grouped_lines>(?:(?:[ ]{{4}}(?:[^*]|\*\*).*\n)|\n)*)"
    )

    matches = re.finditer(
        section,
        file_content_str,
        re.IGNORECASE | re.MULTILINE,
    )

    full_content = []
    last_match_end = -1
    for match in matches:
        full_content += file_content_str[last_match_end + 1 : match.start()].split("\n")
        last_match_end = match.end()

        subsection_content = match.group(0)

        groups = match.groupdict()

        new_content = [f"#### {groups['heading']}\n"]

        if groups["heading"] == "Parameters":
            submatches = re.finditer(
                subsection,
                groups["section_body"],
                re.IGNORECASE | re.MULTILINE,
            )

            for submatch in submatches:
                submatch_groups = submatch.groupdict()
                new_content.append(
                    f"* `{submatch_groups['list_item_name']}` {submatch_groups['list_item_body']}"
                )

                grouped_lines = submatch_groups["grouped_lines"].split("\n")
                while grouped_lines and not grouped_lines[-1]:
                    del grouped_lines[-1]

                final_lines = []
                for line in grouped_lines:
                    final_lines.append(line.replace("        ", "    "))

                new_content += final_lines
                new_content.append("")

        else:
            body_lines = groups["section_body"].split("\n")
            while body_lines and not body_lines[-1]:
                del body_lines[-1]

            final_lines = []
            for line in body_lines:
                final_lines.append(line.replace("    ", "  "))

            final_lines[0] = f"* {final_lines[0].lstrip()}"

            new_content += final_lines
            new_content.append("")

        full_content += new_content

    merged_content = "\n".join(full_content)

    if merged_content:
        file_content = io.StringIO(merged_content).readlines()
    else:
        file_content = io.StringIO(file_content_str).readlines()

        if file_content[0].startswith("# "):
            return "".join(file_content[1:])
        else:
            return "".join(file_content)

    print("Length of content:", len(file_content))

    first_pass = []
    last_was_newline = False

    if not file_content[0].startswith("# "):
        first_pass.append(file_content[0])

    if file_content[1] != "\n":
        first_pass.append(file_content[1])

    # * **src** (*Union**[**str**, **bytes**]*) –
    bad_italics_pattern: Any = r"(?P<prefix>[ ]*[*-] )`(?P<param_name>.+?)` \(\*(?P<type_op>[a-z]+)\*\*(?P<type_vals>\[.*?\])\*\)(?P<remaining>.*)"
    bad_italics_pattern = re.compile(bad_italics_pattern, re.IGNORECASE)

    # # * **Parameters**
    # subheading_pattern: Any = r"\* \*\*(Parameters|Return type|Returns|Raises|.+)\*\*"
    # subheading_pattern = re.compile(subheading_pattern, re.IGNORECASE)

    # four_space_pattern: Any = r"([ ]{4})+(\* \*{2}.+)"
    # four_space_pattern = re.compile(four_space_pattern, re.IGNORECASE)

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

            result = bad_italics_pattern.match(line)
            if result:
                groups = result.groupdict()
                line = f"{groups['prefix']}`{groups['param_name']}` (<em>{groups['type_op']}{groups['type_vals']}</em>){groups['remaining']}"

            # result = subheading_pattern.match(line)
            # if result:
            #     line = f"##### {result.group(1)}"

            # result = four_space_pattern.match(line)
            # if result:
            #     num_groups = len(result.groups())
            #     indent = "  " * (num_groups - 1)
            #     line = f"{indent}{result.group(num_groups)}"
            #     # print(line)
            #     # print(result.groups(), line.rstrip())
            #     # line = f"##### {result.group(1)}"

            if not combined_line:
                if line.startswith("### "):
                    # combined_line.append(line)
                    first_pass.append(line)
                    first_pass.append("\n")
                else:
                    combined_line.append(line.rstrip())
                # combined_line.append("".join(line.split("\n")))
            else:
                combined_line.append(line.strip(" \n"))

    # pprint(first_pass[:200])
    second_pass = []
    for line in first_pass:
        if line.startswith("### class"):
            line = line[1:]
        if line.startswith("##"):
            if line[-1] == ".":
                line = line[:-1]

        second_pass.append(line)

    print("Lines at end of second pass:", len(second_pass))
    return "".join(second_pass)


if __name__ == "__main__":
    main()

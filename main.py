import os, sys
import pathlib
from pprint import pprint


def main():
    input_dir = pathlib.Path(os.environ["INPUT_RAWPATH"])
    output_dir = pathlib.Path(os.environ["INPUT_OUTPUTPATH"])

    file_list = []
    for f in input_dir.iterdir():
        base_file_name = f.name.removeprefix("GENERATED_")
        output_file = output_dir / base_file_name

        file_list.append((f.resolve(), output_file.resolve()))

    print(f"::set-output name=testOutput::This is my test output.")

    sys.exit(0)


if __name__ == "__main__":
    main()

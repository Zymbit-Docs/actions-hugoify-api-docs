import os, sys
import pathlib


def main():
    input_dir = pathlib.Path(os.environ["INPUT_PATH"])

    for f in input_dir.iterdir():
        print(f)

    print(f"::set-output name=testOutput::This is my test output.")

    sys.exit(0)


if __name__ == "__main__":
    main()

"""Small runnable entry point, expanded during implementation."""
import argparse
from . import __version__


def main():
    parser = argparse.ArgumentParser(description="Behavioral Research Data Workbench")
    parser.add_argument("--version", action="version", version=__version__)
    parser.parse_args()
    print("Behavioral Research Data Workbench — implementation in progress")


if __name__ == "__main__":
    main()

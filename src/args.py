import argparse


def parse_args(args: list[str]) -> argparse.Namespace:
    arg_parser = argparse.ArgumentParser(
        prog="Memento",
        description="Memory system for AI vtubers.",
    )

    arg_parser.add_argument(
        "-d", "--dump",
        action="store_true",
        help="dump contents of all databases to dump.json file"
    )

    arg_parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="print all debug statements"
    )
    return arg_parser.parse_args(args)


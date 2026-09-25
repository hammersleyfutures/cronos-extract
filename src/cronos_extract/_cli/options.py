# ABOUTME: The command-line parts that subcommands share: the KOD and --compact options, and the Kod they select.
# ABOUTME: --kod is validated as it is parsed, and --crack recovers the KOD with cronos_extract.crack_kod.
import argparse
from typing import cast

from .._api.crack import crack_kod
from .._api.kod import Kod
from .report import Failure

# The result of ArgumentParser.add_subparsers(), to which each subcommand module adds its parser.
type Subcommands = argparse._SubParsersAction[argparse.ArgumentParser]

CRACK_METHODS = ("strucrack", "dbcrack")


def kod_argument(text: str) -> Kod:
    """Parse a --kod value. Raises argparse.ArgumentTypeError with Kod.from_hex's reason when it is not a KOD."""
    try:
        return Kod.from_hex(text)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e)) from e


def kod_options(*, crack: bool = True, compact: bool = True) -> argparse.ArgumentParser:
    """
    A parent parser holding --kod and --nokod, and --crack and --compact unless they are turned off.

    --kod, --nokod and --crack exclude each other. An option turned off still gets its default, None for --crack and
    False for --compact, so selected_kod and the handlers can read all four from every subcommand's arguments.
    """
    parser = argparse.ArgumentParser(add_help=False)
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--kod", type=kod_argument, metavar="HEX", help="decode the records with this KOD table, as 512 hex digits"
    )
    group.add_argument("--nokod", "-n", action="store_true", help="read the records without KOD decoding")
    if crack:
        group.add_argument(
            "--crack", choices=CRACK_METHODS, help="first recover the database's KOD with this method, then use it"
        )
    else:
        parser.set_defaults(crack=None)
    if compact:
        parser.add_argument(
            "--compact",
            action="store_true",
            help="read the indexes from disk instead of memory, for very large databases; about 15%% slower",
        )
    else:
        parser.set_defaults(compact=False)
    return parser


def selected_kod(args: argparse.Namespace) -> Kod | None:
    """
    The KOD that the options in `args` select: --kod's, None for --nokod, the one --crack recovers from the database
    in args.dbdir, or the default KOD.

    Raises Failure when --crack recovers no KOD, and CronosError or OSError when --crack cannot read the database.
    """
    if args.kod is not None:
        return cast(Kod, args.kod)
    if args.nokod:
        return None
    if args.crack is not None:
        kod = crack_kod(args.dbdir, args.crack)
        if kod is None:
            raise Failure(
                f"{args.crack} cannot recover the KOD of {args.dbdir}; recover it with "
                f"cronos-extract crack strucrack {args.dbdir} and pass it with --kod"
            )
        return kod
    return Kod.default()

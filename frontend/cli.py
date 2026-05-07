import argparse
import sys
from collections.abc import Sequence

from backend import ChatConfig
from backend.core.username import (
    USERNAME_RULES_SUMMARY,
    UsernameValidationError,
    username_requirements_text,
    validate_username,
)

DEV_LOCAL_MODES = {'host', 'join'}


def _username_argument(value: str) -> str:
    """Argparse adapter for canonical username validation."""
    try:
        return validate_username(value)
    except UsernameValidationError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _build_default_parser() -> argparse.ArgumentParser:
    """Build the public CLI parser that defaults to relay mode."""
    parser = argparse.ArgumentParser(
        prog='ogham',
        description='Minimal in-terminal relay chat',
        epilog=(f'{USERNAME_RULES_SUMMARY}.\n{username_requirements_text()}'),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        'mode',
        nargs='?',
        choices=['relay'],
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        '--name',
        type=_username_argument,
        default=None,
        help=USERNAME_RULES_SUMMARY,
    )
    return parser


def _build_dev_parser() -> argparse.ArgumentParser:
    """Build developer-only parsers for local host/join testing."""
    parser = argparse.ArgumentParser(
        prog='ogham',
        description='Developer-only local testing modes for Ogham Chat',
        epilog=(f'{USERNAME_RULES_SUMMARY}.\n{username_requirements_text()}'),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest='mode', required=True)

    host_parser = subparsers.add_parser(
        'host', help='Run host and join from this terminal'
    )
    host_parser.add_argument('--port', type=int, default=9000)
    host_parser.add_argument(
        '--name',
        type=_username_argument,
        default='hostdev',
        help=USERNAME_RULES_SUMMARY,
    )

    join_parser = subparsers.add_parser(
        'join', help='Join an existing local host'
    )
    join_parser.add_argument('--host', default='127.0.0.1')
    join_parser.add_argument('--port', type=int, default=9000)
    join_parser.add_argument(
        '--name',
        type=_username_argument,
        default='guestdev',
        help=USERNAME_RULES_SUMMARY,
    )
    return parser


def parse_args(argv: Sequence[str] | None = None) -> ChatConfig:
    """Parse CLI arguments and build a validated chat configuration."""
    raw_args = list(argv) if argv is not None else sys.argv[1:]

    if raw_args and raw_args[0] in DEV_LOCAL_MODES:
        args = _build_dev_parser().parse_args(raw_args)

        if args.mode == 'host':
            return ChatConfig(
                mode='host',
                requested_username=args.name,
                username=args.name,
                host='127.0.0.1',
                port=args.port,
            )

        return ChatConfig(
            mode='join',
            requested_username=args.name,
            username=args.name,
            host=args.host,
            port=args.port,
        )

    args = _build_default_parser().parse_args(raw_args)

    return ChatConfig(
        mode='relay',
        requested_username=args.name,
        username=None,
        onboarding_required=args.name is None,
    )

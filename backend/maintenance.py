import argparse
import os
import sys

from backend.store.sql import SQLMessageStore


def _build_parser() -> argparse.ArgumentParser:
    """Build the maintenance CLI parser and subcommands."""
    parser = argparse.ArgumentParser(
        description='Ogham Chat maintenance commands'
    )
    subparsers = parser.add_subparsers(dest='command', required=True)

    purge_parser = subparsers.add_parser(
        'purge-expired',
        help='Delete chat messages older than the configured retention window',
    )
    purge_parser.add_argument(
        '--retention-days',
        type=int,
        default=180,
        help='Keep messages newer than this many days (default: 180)',
    )

    return parser


def main() -> int:
    """Run maintenance commands and return process exit code."""
    parser = _build_parser()
    args = parser.parse_args()

    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        parser.error('DATABASE_URL must be set for maintenance commands')

    if args.retention_days < 1:
        parser.error('--retention-days must be at least 1')

    store = SQLMessageStore(database_url)

    if args.command == 'purge-expired':
        deleted_count = store.purge_expired(
            retention_days=args.retention_days,
        )
        print(
            f'Deleted {deleted_count} expired chat messages '
            f'(retention: {args.retention_days} days).'
        )
        return 0

    parser.error(f'Unsupported command: {args.command}')
    return 2


if __name__ == '__main__':
    sys.exit(main())

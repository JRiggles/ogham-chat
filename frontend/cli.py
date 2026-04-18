import argparse

from backend import ChatConfig


def parse_args() -> ChatConfig:
    """Parse CLI arguments and build a validated chat configuration."""
    parser = argparse.ArgumentParser(
        description='Minimal local terminal chat with Textual'
    )
    subparsers = parser.add_subparsers(dest='mode', required=True)

    host_parser = subparsers.add_parser(
        'host', help='Run host and join from this terminal'
    )
    host_parser.add_argument('--port', type=int, default=9000)
    host_parser.add_argument('--name', default='host')

    join_parser = subparsers.add_parser(
        'join', help='Join an existing local host'
    )
    join_parser.add_argument('--host', default='127.0.0.1')
    join_parser.add_argument('--port', type=int, default=9000)
    join_parser.add_argument('--name', default='guest')

    relay_parser = subparsers.add_parser(
        'relay', help='Join remote relay endpoint'
    )
    relay_parser.add_argument(
        '--url',
        default='wss://ogham-chat.fastapicloud.dev/api/v1/ws',
    )
    relay_parser.add_argument('--name', default='guest')

    args = parser.parse_args()

    if args.mode == 'host':
        return ChatConfig(
            mode='host',
            username=args.name,
            host='127.0.0.1',
            port=args.port,
        )

    if args.mode == 'relay':
        return ChatConfig(
            mode='relay',
            username=args.name,
            relay_url=args.url,
        )

    return ChatConfig(
        mode='join',
        username=args.name,
        host=args.host,
        port=args.port,
    )

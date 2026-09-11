"""Launch the React/API server with explicit host, port and development reload."""
import argparse

from dao_vang.config.settings import AppSettings


def main() -> None:
    settings = AppSettings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("legacy_port", nargs="?", type=int)
    parser.add_argument("--port", type=int)
    parser.add_argument("--host", default=settings.web.host)
    parser.add_argument("--reload", action="store_true")
    args = parser.parse_args()
    port = args.port if args.port is not None else args.legacy_port if args.legacy_port is not None else settings.web.port
    if not 1 <= port <= 65535:
        parser.error("port must be between 1 and 65535")
    if args.reload:
        from dao_vang.web.dev_server import main as run_dev
        run_dev(port=port, host=args.host)
        return
    from dao_vang.web.api_server import run_server
    run_server(port=port, host=args.host)

if __name__ == "__main__":
    main()

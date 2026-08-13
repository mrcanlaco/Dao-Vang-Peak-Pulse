import sys
from pathlib import Path
from dao_vang.config.settings import AppSettings
from dao_vang.web.api_server import run_server

def main() -> None:
    """Run the Đảo Vàng Signal Command Center web application."""
    settings = AppSettings()
    port = settings.web.port
    host = "0.0.0.0"

    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        port = int(sys.argv[1])

    print(f"🚀 Starting Đảo Vàng Signal Command Center at http://{host}:{port}")
    run_server(port=port, host=host)

if __name__ == "__main__":
    main()

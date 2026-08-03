import sys
from pathlib import Path

import streamlit.web.cli as stcli


def main() -> None:
    """Run the Streamlit application."""
    app_path = Path(__file__).parent / "app.py"
    
    # Use streamlit's own CLI so it hooks up to the main thread properly
    sys.argv = ["streamlit", "run", str(app_path)]
    sys.exit(stcli.main())


if __name__ == "__main__":
    main()

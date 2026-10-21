import argparse
from pathlib import Path

import uvicorn

from .api import create_app


def main():
    parser = argparse.ArgumentParser(description="Run the local synthetic signup service")
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8121)
    args = parser.parse_args()
    uvicorn.run(create_app(args.database), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()

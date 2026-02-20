"""Export OpenAPI schema to engine/openapi.json."""

from __future__ import annotations

import json
from pathlib import Path

from .api import app


def main() -> None:
    schema = app.openapi()
    output = Path(__file__).resolve().parents[1] / "openapi.json"
    output.write_text(json.dumps(schema, indent=2), encoding="utf-8")
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()

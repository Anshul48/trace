"""Trace V2 ASGI entry point.

The former document-oriented API is intentionally not mounted. Trace V2 has a
single versioned, headless public surface under ``/v2``.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "src")))

from trace.v2.api import create_app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

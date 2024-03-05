"""
This file defines sql as a submodule of buffers/databases/coq.
"""

from pathlib import Path

from .....shared.sql import loader

sql = loader(Path(__file__).resolve(strict=True).parent)

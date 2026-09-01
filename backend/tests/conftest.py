import os
import tempfile
from pathlib import Path

TEST_DIR = Path(tempfile.mkdtemp(prefix="netmonitor-tests-"))
os.environ["NETMONITOR_TEST_DIR"] = str(TEST_DIR)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{(TEST_DIR / 'source.db').as_posix()}"
os.environ["SECRET_KEY"] = "automated-test-secret"

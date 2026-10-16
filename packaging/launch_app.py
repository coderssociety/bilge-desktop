import multiprocessing
import sys

# The graphics card probe runs in a child process, which a frozen program starts as itself; the child stops here,
# before the app itself is imported.
multiprocessing.freeze_support()

from bilge.app.main import main  # noqa: E402

sys.exit(main())

"""DocuSense bounded recovery/redispatch/expiry process entry point."""

from .backend_runtime.entrypoints import run_reconciler


if __name__ == "__main__":
    run_reconciler()

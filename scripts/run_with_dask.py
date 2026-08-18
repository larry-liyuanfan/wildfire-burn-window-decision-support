"""Start a bounded Dask cluster inside an existing Slurm allocation."""

from __future__ import annotations

import argparse
import os

from burnwindows.cli import main as cli_main


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=int(os.environ.get("BURN_DASK_WORKERS", "1")))
    parser.add_argument("--threads-per-worker", type=int, default=1)
    parser.add_argument("--memory-limit", default="0")
    parser.add_argument("args", nargs=argparse.REMAINDER)
    options = parser.parse_args()
    if options.workers < 1:
        parser.error("workers must be positive")
    from dask.distributed import Client, LocalCluster

    with LocalCluster(
        n_workers=options.workers,
        threads_per_worker=options.threads_per_worker,
        memory_limit=options.memory_limit,
        dashboard_address=None,
    ) as cluster, Client(cluster):
        forwarded = options.args[1:] if options.args[:1] == ["--"] else options.args
        return cli_main(forwarded)


if __name__ == "__main__":
    raise SystemExit(main())


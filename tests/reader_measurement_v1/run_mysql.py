#!/usr/bin/env python3
"""Explicit local ephemeral DB simulation. No production network or data.

Uses only already-cached pinned images, no exposed port and a --network none
database container. PHP workers join that isolated loopback namespace.
"""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
DB_IMAGE = "mariadb@sha256:ae6119716edac6998ae85508431b3d2e666530ddf4e94c61a10710caec9b0f71"
PHP_IMAGE = "wordpress@sha256:8801a1239d7ba9fb340a5fc5ba0bf7f8d3652adbd64893e3fba7992ba618108e"


def run(args, **kwargs):
    result = subprocess.run(args, capture_output=True, text=True, check=False, **kwargs)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result


def main():
    name = "raos-reader-measurement-test-" + str(os.getpid())
    started = False
    try:
        run(["docker","run","--pull=never","--rm","-d","--name",name,"--network","none",
             "--read-only","--cap-drop=ALL","--security-opt","no-new-privileges","--user","mysql",
             "--tmpfs","/var/lib/mysql:rw,nosuid,uid=999,gid=999,mode=0700,size=256m",
             "--tmpfs","/run/mysqld:rw,nosuid,uid=999,gid=999,mode=0700,size=16m",
             "--tmpfs","/tmp:rw,nosuid,size=32m",
             "-e","MARIADB_ALLOW_EMPTY_ROOT_PASSWORD=1","-e","MARIADB_DATABASE=raos_reader_test",
             DB_IMAGE,"--bind-address=127.0.0.1"],timeout=20)
        started = True
        deadline = time.monotonic() + 30
        while True:
            ready = subprocess.run(["docker","exec",name,"mariadb-admin","--protocol=tcp","--host=127.0.0.1","ping","--silent"],capture_output=True)
            if ready.returncode == 0:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError("ephemeral database did not become ready")
            time.sleep(.3)
        base = ["docker","run","--pull=never","--rm","--network","container:"+name,
                "--read-only","--cap-drop=ALL","--security-opt","no-new-privileges",
                "--tmpfs","/tmp:rw,noexec,nosuid,size=16m",
                "--mount","type=bind,src="+str(ROOT)+",dst="+str(ROOT)+",readonly",
                "--workdir",str(ROOT),"--entrypoint","php",PHP_IMAGE,
                "tests/reader_measurement_v1/mysql.php"]
        print(run(base+["setup"],timeout=20).stdout.strip())
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _:json.loads(run(base+["record"],timeout=45).stdout),range(8)))
        assert sum(row["accepted"] for row in results) == 1200, results
        assert sum(row["limited"] for row in results) == 400, results
        print(run(base+["verify"],timeout=20).stdout.strip())
        print("8 concurrent workers: 1200 accepted / 400 limited; no external network.")
    finally:
        if started:
            subprocess.run(["docker","stop","--time","3",name],capture_output=True,timeout=10)


if __name__ == "__main__":
    main()

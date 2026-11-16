"""Cold snapshot and quarantined empty-volume restore for a trusted single-host bundle."""

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
import uuid
import zlib
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

import yaml

if __package__:
    from . import single_host
    from .deerflow_lock import read_revision
else:
    import single_host
    from deerflow_lock import read_revision

ROOT = Path(__file__).resolve().parents[1]
FORMAT = "deermate-cold-snapshot-v1"
NAME = re.compile(r"[a-z][a-z0-9-]{0,39}\Z")
MAX_BYTES = 16 * 1024**3
MAX_ARCHIVE_BYTES = MAX_BYTES + 128 * 1024**2
REQUIRED = {
    "bundle/bundle.json",
    "bundle/.env",
    "bundle/runtime/config.yaml",
    "bundle/runtime/nginx.conf",
    "bundle/runtime.env",
    "bundle/control.env",
    "bundle/frontend.env",
    "home/data/deerflow.db",
}
SNAPSHOT_WORKER = r"""
import base64,hashlib,io,json,shutil,sqlite3,sys,tarfile,tempfile
from pathlib import Path
request=json.load(sys.stdin)
request_config=request.pop('configuration')
home=Path('/state')
files={}
request['excluded_rebuildable_paths']=['.cache/uv','deermate/.cache/uv']
for p in sorted(home.rglob('*')):
    relative=p.relative_to(home).as_posix()
    if any(relative==c or relative.startswith(c+'/')
           for c in request['excluded_rebuildable_paths']):
        continue
    if p.is_symlink() or (not p.is_file() and not p.is_dir()):
        raise RuntimeError('Unsupported state link or special file; review it separately')
    if p.is_file():
        key='home/'+p.relative_to(home).as_posix()
        with p.open('rb') as source:
            digest=hashlib.file_digest(source,'sha256').hexdigest()
        files[key]={'size':p.stat().st_size,'sha256':digest,'mode':p.stat().st_mode&0o777}
for name,item in request_config.items():
    blob=base64.b64decode(item['data'])
    files['bundle/'+name]={'size':len(blob),'sha256':hashlib.sha256(blob).hexdigest(),'mode':item['mode']}
request['files']=files
database=home/'data/deerflow.db'
inventory={name:[] for name in ('operations','tasks','memory_operations','memory_jobs','runs')}
if database.exists():
    # Query a private copy: even SQLite reader locks must not alter the source WAL/SHM.
    with tempfile.TemporaryDirectory(prefix='snapshot-inventory-') as temp:
        for suffix in ('','-wal','-shm','-journal'):
            source=Path(str(database)+suffix)
            if source.exists():shutil.copyfile(source,Path(temp)/('state.db'+suffix))
        d=sqlite3.connect(str(Path(temp)/'state.db'))
        if d.execute('PRAGMA quick_check').fetchone()[0]!='ok':
            raise RuntimeError('Source database integrity check failed')
        tables={r[0] for r in d.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'deermate_work_records' in tables:
            sql=("SELECT id,state FROM deermate_work_records WHERE kind='operation' "
                 "AND state NOT IN ('settled','completed','failed','cancelled','rejected') "
                 "ORDER BY id")
            inventory['operations']=[{'id':r[0],'state':r[1]} for r in d.execute(sql)]
        if 'mcp_tasks' in tables:
            sql=("SELECT id,status FROM mcp_tasks WHERE status NOT IN "
                 "('completed','failed','cancelled') ORDER BY id")
            inventory['tasks']=[{'id':r[0],'state':r[1]} for r in d.execute(sql)]
        for category,table in (
            ('memory_operations','deermate_memory_operations'),
            ('memory_jobs','deermate_memory_jobs'),
        ):
            if table in tables:
                sql=(f"SELECT id,status FROM {table} WHERE status IN "
                     "('pending','processing','uncertain','dispatching','running') ORDER BY id")
                inventory[category]=[{'id':r[0],'state':r[1]} for r in d.execute(sql)]
        if 'runs' in tables:
            sql=("SELECT run_id,status FROM runs WHERE status IN "
                 "('pending','running','queued','unknown') ORDER BY run_id")
            inventory['runs']=[{'id':r[0],'state':r[1]} for r in d.execute(sql)]
        d.close()
request['inflight_inventory']=inventory
if any(inventory.values()) and not request['inflight_acknowledged']:
    raise RuntimeError('In-flight/unknown work requires explicit reconciliation acknowledgement')
manifest=json.dumps(request,sort_keys=True,indent=2).encode()+bytes([10])
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|gz') as tar:
    info=tarfile.TarInfo('manifest.json');info.size=len(manifest);info.mode=0o600
    tar.addfile(info,io.BytesIO(manifest))
    for name,item in files.items():
        info=tarfile.TarInfo(name);info.size=item['size'];info.mode=item['mode'];info.uid=info.gid=1000
        if name.startswith('home/'):
            with (home/name[5:]).open('rb') as source:tar.addfile(info,source)
        else:
            # Configuration comes from the trusted bundle, not arbitrary container paths.
            blob=base64.b64decode(request_config[name[7:]]['data'])
            tar.addfile(info,io.BytesIO(blob))
"""
RESTORE_WORKER = r"""
import os,shutil,sys,tarfile
from pathlib import Path
os.umask(0o077)
home=Path('/state')
if any(home.iterdir()):raise RuntimeError('Restore target must be empty')
with tarfile.open(fileobj=sys.stdin.buffer,mode='r|gz') as tar:
    for member in tar:
        if not member.name.startswith('home/'):continue
        path=home/member.name[5:]
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('xb') as dest:shutil.copyfileobj(tar.extractfile(member),dest)
        path.chmod(member.mode&0o777)
    for path in [home,*home.rglob('*')]:
        os.chown(path,1000,1000)
"""


class SnapshotError(ValueError):
    pass


def command(argv, *, data=None, timeout=90):
    try:
        result = subprocess.run(
            [str(v) for v in argv],
            input=data,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise SnapshotError("Snapshot command timed out; original data is retained") from error
    if result.returncode:
        # Docker/config/runtime output can contain secrets or personal state.
        raise SnapshotError(f"{Path(argv[0]).name} exited {result.returncode}; data was retained")
    return result.stdout


def compose(bundle, *args):
    return command(
        [
            "docker",
            "compose",
            "--project-directory",
            bundle,
            "--env-file",
            bundle / ".env",
            "--file",
            bundle / "compose.yaml",
            *args,
        ],
        timeout=180,
    )


def inspect(container, field):
    return json.loads(
        command(["docker", "inspect", "--format", "{{json ." + field + "}}", container])
    )


def safe_member(name):
    p = PurePosixPath(name)
    if (
        not name
        or p.is_absolute()
        or ".." in p.parts
        or "\\" in name
        or p.as_posix() != name
        or not name.startswith(("home/", "bundle/"))
    ):
        raise SnapshotError("Invalid archive member path")


def check_tar_metadata(archive, member, mode):
    """Accept the exporter format, not arbitrary filesystem/tar instructions."""
    owner = 0 if member.name == "manifest.json" else 1000
    if member.type != tarfile.REGTYPE:
        raise SnapshotError("Only regular snapshot files are accepted")
    # Check the canonical raw header too, including fields unused by regular
    # file extraction and padding that higher-level APIs need not preserve.
    archive.fileobj.seek(member.offset_data - tarfile.BLOCKSIZE)
    header = archive.fileobj.read(tarfile.BLOCKSIZE)
    if (
        len(header) != tarfile.BLOCKSIZE
        or header[257:265] != tarfile.POSIX_MAGIC
        or any(byte not in {0, 32, 48} for byte in header[329:345])
        or header[500:] != bytes(12)
    ):
        raise SnapshotError("Unsupported snapshot raw tar metadata")
    if (
        type(mode) is not int
        or not 0 <= mode <= 0o777
        or member.mode != mode
        or member.uid != owner
        or member.gid != owner
        or member.uname
        or member.gname
        or member.mtime != 0
        or member.linkname
        or member.devmajor
        or member.devminor
        or member.sparse is not None
    ):
        raise SnapshotError("Snapshot tar metadata mismatch")
    # PAX is needed for UTF-8/long names and large files. No ownership,
    # timestamps, links, sparse maps or vendor extraction instructions survive.
    for key, value in member.pax_headers.items():
        if (key, value) not in {("path", member.name), ("size", str(member.size))}:
            raise SnapshotError("Unsupported snapshot PAX metadata")


def check_manifest(manifest):
    if not isinstance(manifest, dict) or manifest.get("format") != FORMAT:
        raise SnapshotError("Unknown snapshot format")
    identifier = manifest.get("snapshot_id")
    if not isinstance(identifier, str) or str(uuid.UUID(identifier)) != identifier:
        raise SnapshotError("Invalid snapshot identity")
    point = datetime.fromisoformat(manifest["recovery_point"])
    if point.tzinfo is None:
        raise SnapshotError("Snapshot recovery point must include its time zone")
    if not re.fullmatch(r"[0-9a-f]{40}", manifest["upstream_commit"]):
        raise SnapshotError("Invalid snapshot upstream identity")
    if not NAME.fullmatch(manifest["source_project"]):
        raise SnapshotError("Invalid snapshot source project")
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,254}", manifest["source_home_volume"]):
        raise SnapshotError("Invalid snapshot source volume")
    images = manifest.get("images")
    if not isinstance(images, dict) or set(images) != {"control", "gateway", "frontend", "nginx"}:
        raise SnapshotError("Missing snapshot image identity")
    if any(not re.fullmatch(r"sha256:[0-9a-f]{64}", value) for value in images.values()):
        raise SnapshotError("Snapshot images must have immutable Docker IDs")
    inventory = manifest["inflight_inventory"]
    categories = {"operations", "tasks", "memory_operations", "memory_jobs", "runs"}
    if not isinstance(inventory, dict) or set(inventory) != categories:
        raise SnapshotError("Incomplete in-flight inventory")
    for values in inventory.values():
        if not isinstance(values, list) or any(
            not isinstance(row, dict)
            or not isinstance(row.get("id"), str)
            or not row["id"]
            or not isinstance(row.get("state"), str)
            or not row["state"]
            for row in values
        ):
            raise SnapshotError("Invalid in-flight identity")
    if type(manifest["inflight_acknowledged"]) is not bool:
        raise SnapshotError("Invalid in-flight acknowledgement")
    if any(inventory.values()) and not manifest["inflight_acknowledged"]:
        raise SnapshotError("Unacknowledged in-flight state")
    tool = manifest["snapshot_tool"]
    if not isinstance(tool, dict) or not re.fullmatch(r"[0-9a-f]{64}", tool["sha256"]):
        raise SnapshotError("Missing snapshot tool source identity")
    if not isinstance(manifest.get("files"), dict):
        raise SnapshotError("Invalid snapshot file inventory")


def verify_archive(archive):
    members, size = [], 0
    for member in archive:
        members.append(member)
        if member.size < 0:
            raise SnapshotError("Negative snapshot member size")
        size += member.size
        if len(members) > 100_000 or size > MAX_BYTES:
            raise SnapshotError("Snapshot exceeds supported member/size limits")
    names = {m.name for m in members}
    if len(names) != len(members):
        raise SnapshotError("Duplicate archive member")
    if archive.pax_headers:
        raise SnapshotError("Global snapshot PAX headers are unsupported")
    if any(m.type != tarfile.REGTYPE for m in members):
        raise SnapshotError("Only regular snapshot files are accepted")
    meta = archive.getmember("manifest.json")
    check_tar_metadata(archive, meta, 0o600)
    if meta.size > 32 * 1024**2:
        raise SnapshotError("Oversized snapshot manifest")
    manifest = json.load(archive.extractfile(meta))
    check_manifest(manifest)
    files = manifest["files"]
    if not REQUIRED <= files.keys():
        raise SnapshotError("Missing required snapshot component")
    if set(files) | {"manifest.json"} != names:
        raise SnapshotError("Missing or unexpected archive member")
    for member in members:
        if member.name == "manifest.json":
            continue
        safe_member(member.name)
        if any(str(parent) in names for parent in PurePosixPath(member.name).parents):
            raise SnapshotError("Snapshot file and parent path conflict")
        expected = files[member.name]
        if not isinstance(expected, dict):
            raise SnapshotError("Invalid snapshot file metadata")
        check_tar_metadata(archive, member, expected["mode"])
        if (
            type(expected["size"]) is not int
            or expected["size"] != member.size
            or not re.fullmatch(r"[0-9a-f]{64}", expected["sha256"])
            or hashlib.file_digest(archive.extractfile(member), "sha256").hexdigest()
            != expected["sha256"]
        ):
            raise SnapshotError("Snapshot checksum or file metadata mismatch")
    return manifest


@contextmanager
def validated_snapshot(snapshot):
    """Freeze once, validate fully, and keep that same private object for restore."""
    errors = (tarfile.TarError, OSError, EOFError, KeyError, TypeError, ValueError, zlib.error)
    with tempfile.TemporaryFile(mode="w+b") as frozen:
        try:
            with snapshot.open("rb") as source:
                copied = 0
                while chunk := source.read(1024 * 1024):
                    copied += len(chunk)
                    if copied > MAX_ARCHIVE_BYTES:
                        raise SnapshotError("Snapshot archive exceeds supported size")
                    frozen.write(chunk)
            frozen.flush()
            frozen.seek(0)
            archive = tarfile.open(fileobj=frozen, mode="r:gz")
        except SnapshotError:
            raise
        except errors as error:
            raise SnapshotError("Incomplete or invalid snapshot; no target was written") from error
        with archive:
            try:
                manifest = verify_archive(archive)
            except SnapshotError:
                raise
            except errors as error:
                raise SnapshotError(
                    "Incomplete or invalid snapshot; no target was written"
                ) from error
            yield archive, manifest, frozen


def verify_snapshot(snapshot):
    """No Docker or target mutation; apply the same preflight as actual restore."""
    with validated_snapshot(snapshot) as (_, manifest, _):
        return manifest


def tool_identity():
    identity = {
        "sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "git_revision": None,
        "checkout_dirty": None,
    }
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        identity.update(git_revision=revision, checkout_dirty=bool(dirty))
    except (OSError, subprocess.CalledProcessError):
        pass  # Exported source still has its actual content hash outside a Git checkout.
    return identity


def backup(bundle, output, *, acknowledge_inflight=False, keep_stopped=False):
    started = time.monotonic()
    bundle, output = bundle.resolve(), output.resolve()
    if output.exists() or output.is_relative_to(bundle):
        raise SnapshotError("Use a new off-bundle snapshot path; never overwrite a backup")
    info = json.loads((bundle / "bundle.json").read_text())
    ids, images, image_sources = {}, {}, {}
    home = None
    for name in ("gateway", "control", "frontend", "nginx"):
        identifier = compose(bundle, "ps", "--all", "--quiet", name).decode().strip()
        if not identifier or "\n" in identifier:
            raise SnapshotError("Expected one installed container for each single-host service")
        ids[name] = identifier
        images[name] = inspect(identifier, "Image")
        labels = inspect(identifier, "Config.Labels") or {}
        image_sources[name] = {
            key: labels.get(key)
            for key in (
                "org.opencontainers.image.revision",
                "io.deermate.source-sha256",
                "io.deermate.deerflow.commit",
                "io.deermate.upstream-revision",
            )
        }
        if name in {"gateway", "control"}:
            destination = "/app/backend/.deer-flow" if name == "gateway" else "/runtime-home"
            mount = next(
                (m for m in inspect(identifier, "Mounts") if m["Destination"] == destination), {}
            )
            if mount.get("Type") != "volume" or (home is not None and home != mount["Name"]):
                raise SnapshotError("Go and Gateway must share one named home volume")
            home = mount["Name"]
    mountpoint = json.loads(command(["docker", "volume", "inspect", home]))[0]["Mountpoint"]
    if output.is_relative_to(Path(mountpoint)):
        raise SnapshotError("Snapshot must be outside the source state volume")
    config = {}
    for path in sorted(bundle.rglob("*")):
        relative = path.relative_to(bundle).as_posix()
        included = (
            relative in {".env", "compose.yaml", "bundle.json", "start.sh"}
            or ("/" not in relative and path.suffix == ".env")
            or relative.startswith(("runtime/", "edge/"))
        )
        if included and path.is_symlink():
            raise SnapshotError("Configuration links must be reviewed separately")
        if included and path.is_file():
            config[relative] = {
                "data": base64.b64encode(path.read_bytes()).decode(),
                "mode": path.stat().st_mode & 0o777,
            }
    running = [
        name
        for name in compose(bundle, "ps", "--status", "running", "--services").decode().splitlines()
        if name in {"gateway", "control", "frontend", "nginx", "edge"}
    ]
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(prefix=".cold-snapshot-", dir=output.parent)
    os.fchmod(descriptor, 0o600)
    try:
        # Close ingress first, then stop every application writer at the same recovery point.
        ingress = [n for n in running if n in {"nginx", "edge"}]
        if ingress:
            compose(bundle, "stop", "--timeout", "60", *ingress)
        writers = [n for n in running if n not in {"nginx", "edge"}]
        if writers:
            compose(bundle, "stop", "--timeout", "60", *writers)
        for identifier in (
            command(["docker", "ps", "--filter", f"volume={home}", "--quiet"]).decode().splitlines()
        ):
            if any(m.get("Name") == home and m.get("RW") for m in inspect(identifier, "Mounts")):
                raise SnapshotError("Another running writer shares the home volume")
        request = {
            "format": FORMAT,
            "snapshot_id": str(uuid.uuid4()),
            "recovery_point": datetime.now(UTC).isoformat(),
            "images": images,
            "image_source_labels": image_sources,
            "snapshot_tool": tool_identity(),
            "upstream_commit": info["upstream_pin"],
            "source_project": info["project"],
            "source_home_volume": home,
            "inflight_acknowledged": acknowledge_inflight,
            "configuration": config,
            "scope": (
                "All durable home files and bundle configuration; "
                "external Worker/native state is not copied"
            ),
            "privacy": "Contains private data and keys; checksums are not origin authentication",
        }
        export_started = time.monotonic()
        with os.fdopen(descriptor, "wb") as target:
            result = subprocess.run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--interactive",
                    "--network=none",
                    "--user=1000:1000",
                    "--cap-drop=ALL",
                    "--mount",
                    f"type=volume,source={home},target=/state,readonly",
                    "--entrypoint=/app/backend/.venv/bin/python",
                    images["gateway"],
                    "-c",
                    SNAPSHOT_WORKER,
                ],
                input=json.dumps(request).encode(),
                stdout=target,
                stderr=subprocess.PIPE,
                timeout=300,
            )
            target.flush()
            os.fsync(target.fileno())
        export_seconds = time.monotonic() - export_started
        if result.returncode:
            diagnostic = output.parent / (".snapshot-" + request["snapshot_id"] + ".error.log")
            fd = os.open(diagnostic, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as log:
                log.write(result.stderr[-65536:])
            raise SnapshotError("Cold export failed; private diagnostics: " + str(diagnostic))
        manifest = verify_snapshot(Path(temporary))
        os.link(temporary, output)
        return {
            "snapshot_id": manifest["snapshot_id"],
            "recovery_point": manifest["recovery_point"],
            "files": len(manifest["files"]),
            "archive_export_seconds": round(export_seconds, 3),
            "backup_to_verified_archive_seconds": round(time.monotonic() - started, 3),
        }
    finally:
        Path(temporary).unlink(missing_ok=True)
        if running and not keep_stopped:
            compose(bundle, "up", "--detach", "--wait", "--wait-timeout", "240", *running)


def restore(snapshot, output, project, port):
    started = time.monotonic()
    with validated_snapshot(snapshot) as (archive, manifest, frozen):
        verified_seconds = time.monotonic() - started
        return restore_validated(
            archive, manifest, frozen, output, project, port, started, verified_seconds
        )


def configure_quarantine(output, services):
    services.setdefault("networks", {}).setdefault("default", {})["internal"] = True
    services["networks"].setdefault("edge", {})
    services["services"]["nginx"]["networks"] = ["default", "edge"]
    for name in ("gateway", "control", "frontend", "nginx"):
        services["services"][name].setdefault("environment", {}).update(
            {
                "DEERMATE_TELEMETRY_ENABLED": "false",
                "OTEL_SDK_DISABLED": "true",
            }
        )
    control = services["services"]["control"]["environment"]
    control.update({"DEERMATE_RESTORE_QUARANTINE": "true", "DEERMATE_CONTINUOUS_ENABLED": "false"})
    runtime = services["services"]["gateway"]
    runtime["environment"]["PYTHONPATH"] = "/etc/deermate:/app/backend"
    runtime["environment"]["DEER_FLOW_EXTENSIONS_CONFIG_PATH"] = (
        "/etc/deermate/restore-extensions.json"
    )
    (output / "runtime/restore-extensions.json").write_text('{"mcpServers":{},"skills":{}}\n')
    (output / "runtime/restore-extensions.json").chmod(0o644)
    (output / "runtime").chmod(0o755)
    for directory in (output / "runtime").rglob("*"):
        if directory.is_dir():
            directory.chmod(0o755)
    config_path = output / "runtime/config.yaml"
    cfg = yaml.safe_load(config_path.read_text())
    cfg["extensions"]["mcpServers"] = {}
    cfg["scheduler"] = {"enabled": False}
    cfg.setdefault("mcp_tasks", {})["enabled"] = False
    cfg.setdefault("subagent_batches", {})["enabled"] = False
    cfg.setdefault("projects", {})["summaries_enabled"] = False
    config_path.write_text(yaml.safe_dump(cfg, sort_keys=False))
    return services


def restore_validated(archive, manifest, frozen, output, project, port, started, verified_seconds):
    if not NAME.fullmatch(project) or not 1024 <= port <= 65535 or output.exists():
        raise SnapshotError("Use a fresh bundle, valid project and unprivileged port")
    if manifest["upstream_commit"] != read_revision():
        raise SnapshotError("Use the matching upstream/tool version before restoration")
    for image in manifest["images"].values():
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
            raise SnapshotError("Snapshot images must have immutable Docker IDs")
        command(["docker", "image", "inspect", image])
    probe = "deermate-restore-probe-" + uuid.uuid4().hex[:12]
    try:
        result = command(
            [
                "docker",
                "run",
                "--name",
                probe,
                "--rm",
                "--network=none",
                "--entrypoint=/deermate",
                manifest["images"]["control"],
                "capabilities",
            ],
            timeout=8,
        )
        if "restore-quarantine-v1" not in json.loads(result).get("capabilities", []):
            raise SnapshotError("Control image lacks mandatory restore quarantine")
    finally:
        subprocess.run(["docker", "rm", "--force", probe], capture_output=True)
    volume = project + "-restored-home"
    existing = (
        command(["docker", "volume", "ls", "--format", "{{.Name}}", "--filter", f"name=^{volume}$"])
        .decode()
        .splitlines()
    )
    if existing:
        raise SnapshotError("Restore target volume already exists; original state was retained")
    # Validation, immutable images and quarantine capability all precede target writes.
    output.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    output.mkdir(mode=0o700)
    for member in archive.getmembers():
        if not member.name.startswith("bundle/"):
            continue
        target = output / member.name[7:]
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        target.write_bytes(archive.extractfile(member).read())
        target.chmod(member.mode)
    services = single_host.compose(project, port)
    services["volumes"]["home"] = {"external": True, "name": volume}
    services = configure_quarantine(output, services)
    (output / "compose.yaml").write_text(yaml.safe_dump(services, sort_keys=False))
    env = {"COMPOSE_PROJECT_NAME": project, "DEERMATE_STAGE_VOLUME": project + "-stage"}
    env.update({f"DEERMATE_{n.upper()}_IMAGE": image for n, image in manifest["images"].items()})
    (output / ".env").write_text("".join(f"{k}={v}\n" for k, v in env.items()))
    (output / ".env").chmod(0o600)
    shutil.copyfile(ROOT / "deploy/single-host/start.sh", output / "start.sh")
    shutil.copyfile(ROOT / "deploy/single-host/init.py", output / "runtime/single_host_init.py")
    (output / "start.sh").chmod(0o700)
    info = json.loads((output / "bundle.json").read_text())
    info.update(
        project=project, port=port, restore_quarantine=True, snapshot_id=manifest["snapshot_id"]
    )
    (output / "bundle.json").write_text(json.dumps(info, indent=2) + "\n")
    command(
        [
            "docker",
            "volume",
            "create",
            "--label",
            f"io.deermate.snapshot={manifest['snapshot_id']}",
            volume,
        ]
    )
    copy_started = time.monotonic()
    frozen.seek(0)
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--interactive",
            "--network=none",
            "--user=0:0",
            "--cap-drop=ALL",
            "--cap-add=CHOWN",
            "--cap-add=DAC_OVERRIDE",
            "--cap-add=FOWNER",
            "--mount",
            f"type=volume,source={volume},target=/state",
            "--entrypoint=/app/backend/.venv/bin/python",
            manifest["images"]["gateway"],
            "-c",
            RESTORE_WORKER,
        ],
        stdin=frozen,
        capture_output=True,
        timeout=300,
    )
    if result.returncode:
        raise SnapshotError(
            "Restore stopped; partial target retained for inspection, never auto-started"
        )
    result = {
        "snapshot_id": manifest["snapshot_id"],
        "recovery_point": manifest["recovery_point"],
        "restored_seconds": round(time.monotonic() - started, 3),
        "archive_validation_seconds": round(verified_seconds, 3),
        "archive_copy_seconds": round(time.monotonic() - copy_started, 3),
        "quarantine": True,
        "source_volume_preserved": True,
        "inflight_inventory": manifest["inflight_inventory"],
        "scope": (
            "Archive verification, bundle generation and empty-volume copy; "
            "service readiness is measured separately"
        ),
    }
    (output / "restore-receipt.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    export = sub.add_parser("backup")
    export.add_argument("--bundle", type=Path, required=True)
    export.add_argument("--output", type=Path, required=True)
    export.add_argument("--acknowledge-inflight", action="store_true")
    export.add_argument("--keep-stopped", action="store_true")
    check = sub.add_parser("verify")
    check.add_argument("--snapshot", type=Path, required=True)
    load = sub.add_parser("restore")
    load.add_argument("--snapshot", type=Path, required=True)
    load.add_argument("--output", type=Path, required=True)
    load.add_argument("--project", required=True)
    load.add_argument("--port", type=int, default=2028)
    args = parser.parse_args()
    try:
        if args.action == "backup":
            result = backup(
                args.bundle,
                args.output,
                acknowledge_inflight=args.acknowledge_inflight,
                keep_stopped=args.keep_stopped,
            )
        elif args.action == "verify":
            manifest = verify_snapshot(args.snapshot)
            result = {
                "snapshot_id": manifest["snapshot_id"],
                "verified": True,
                "files": len(manifest["files"]),
            }
        else:
            result = restore(
                args.snapshot.resolve(), args.output.resolve(), args.project, args.port
            )
        print(json.dumps(result, indent=2))
    except (SnapshotError, OSError, ValueError, subprocess.TimeoutExpired) as error:
        message = str(error) if isinstance(error, SnapshotError) else type(error).__name__
        parser.exit(1, f"Snapshot operation stopped: {message}\n")


if __name__ == "__main__":
    main()

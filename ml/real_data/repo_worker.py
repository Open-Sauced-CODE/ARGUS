"""
ARGUS Phase 5, Step 4 - the per-repository worker (kept in its own module so Windows multiprocessing can import it).
"""

from ml.real_data import terrads_source as ts
from ml.real_data.tf_normalise import normalise_repo


def process_repo(job):
    """job: dict with id, full_name, license, commit, bucket, archive_root, local_dir, max_file_bytes.
    Returns a plain dict (safe to send between processes)."""
    result = {"id": job["id"], "found": False, "records": [], "skips": {}, "seen": {}, "files_parsed": 0,
              "parse_errors": 0, "too_large": 0, "error": None}
    try:
        if job.get("local_dir"):
            files = ts.read_dir_files(job["local_dir"], job["max_file_bytes"])
        else:
            files = ts.read_repo_files(job["archive_root"], job["id"], job["max_file_bytes"])
        if files is None:
            return result
        result["found"] = True
        result["too_large"] = files.pop("__too_large__", 0)
        out = normalise_repo(files)
    except Exception as exc:  # one broken repository must never stop a long run
        result["error"] = "{}: {}".format(type(exc).__name__, str(exc)[:200])
        return result
    result["skips"] = dict(out["skips"])
    result["seen"] = dict(out["seen"])
    result["files_parsed"] = out["files_parsed"]
    result["parse_errors"] = out["parse_errors"]
    for rec in out["records"]:
        rec["source"].update({"repo_id": job["id"], "repo": job["full_name"], "commit": job["commit"],
                              "license": job["license"], "bucket": job["bucket"]})
        result["records"].append(rec)
    return result

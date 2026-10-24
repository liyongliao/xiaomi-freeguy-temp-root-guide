#!/usr/bin/env python3
"""Fixed, nonpersistent diagnostic checks for one verified Xiaomi build."""
import argparse
import json
import re
import secrets
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

EXPECTED = {
    "ro.product.device": "freeguy",
    "ro.build.version.sdk": "34",
    "ro.product.cpu.abilist": "armeabi-v7a,armeabi",
    "ro.build.fingerprint": "xiaomi/freeguy/freeguy:14/UQ1A.240105.004.A1/OS3.0.106.0.UFTMATV:user/release-keys",
}
PROBES = {
    "identity": "id",
    "context": "cat /proc/self/attr/current",
    "capabilities": "grep Cap /proc/self/status",
    "boot_access": "test -r /dev/block/mmcblk0p25&&echo READABLE||echo DENIED",
    "policy_access": "test -w /sys/fs/selinux/load&&echo WRITABLE||echo DENIED",
}


def make_command(probe, tag):
    if probe not in PROBES:
        raise ValueError("Unknown fixed probe")
    if not re.fullmatch(r"TVR[0-9a-f]{7}", tag):
        raise ValueError("Unexpected log tag")
    command = f"({PROBES[probe]}) 2>&1|log -t {tag}"
    if len(command.encode("utf-8")) > 91:
        raise ValueError("Diagnostic command exceeds the 91-byte property limit")
    return command


def matching_build(properties):
    return all(properties.get(key) == value for key, value in EXPECTED.items())


def log_lines(raw):
    return [line for line in raw.splitlines()
            if line.strip() and not line.startswith("--------- beginning of ")]


def classify(probes):
    identity = probes.get("identity", {}).get("output", "")
    context = probes.get("context", {}).get("output", "").strip()
    verified = bool(re.search(r"\buid=0\(root\)", identity)) and context == "u:r:misysdiagnose:s0"
    return {
        "restricted_diagnostic_uid0_verified": verified,
        "full_temporary_root_verified": False,
        "partition_backup_completed": False,
        "note": "UID 0 / access probes alone do not establish full Root or a partition backup.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", required=True, help="Explicit adb serial, such as TV_IP:5555")
    parser.add_argument("--adb", default="adb", help="adb executable")
    parser.add_argument("--diagnostic", action="store_true", help="Run the five fixed UID 0 probes")
    parser.add_argument("--output", type=Path, help="New local directory for evidence")
    args = parser.parse_args()

    def adb(*arguments):
        result = subprocess.run([args.adb, "-s", args.serial, *arguments],
                                capture_output=True, text=True, timeout=20)
        if result.returncode:
            raise RuntimeError(f"adb failed ({result.returncode}): {result.stderr.strip()}")
        return result.stdout.strip()

    report = {"date_utc": datetime.now(timezone.utc).isoformat(), "properties": {}, "probes": {}}
    # Do not put IPs, hardware serials, accounts or the complete getprop dump in the report.
    if args.output:
        args.output.mkdir(parents=True, exist_ok=False)
    try:
        if adb("get-state") != "device":
            raise RuntimeError("Selected device is not authorized and online")
        report["properties"] = {key: adb("shell", "getprop " + key) for key in EXPECTED}
        report["before"] = {
            "shell_identity": adb("shell", "id"),
            "selinux": adb("shell", "getenforce"),
            "verified_boot": adb("shell", "getprop ro.boot.verifiedbootstate"),
            "slot": adb("shell", "getprop ro.boot.slot_suffix"),
            "boot_a": adb("shell", "readlink -f /dev/block/by-name/boot_a"),
        }
        if not matching_build(report["properties"]):
            raise RuntimeError("Build does not exactly match the verified device; no diagnostic calls made")
        print("Matched freeguy / OS3.0.106.0.UFTMATV")
        if args.diagnostic:
            if report["before"]["selinux"] != "Enforcing":
                raise RuntimeError("SELinux differs from the verified baseline; no diagnostic calls made")
            if report["before"]["boot_a"] != "/dev/block/mmcblk0p25":
                raise RuntimeError("boot_a mapping differs; no diagnostic calls made")
            if adb("shell", "service check TvService") != "Service TvService: found":
                raise RuntimeError("TvService is unavailable")
            prefix = "TVR" + secrets.token_hex(3)
            for index, probe in enumerate(PROBES):
                tag = prefix + str(index)
                command = make_command(probe, tag)
                reply = adb("shell", "service call TvService 4400 s16 s s16 " + shlex.quote(command))
                deadline = time.monotonic() + 12
                lines = []
                while time.monotonic() < deadline:
                    time.sleep(0.35)
                    lines = log_lines(adb("shell", f"logcat -d -v raw -s {tag}:I '*:S'"))
                    if lines:
                        break
                report["probes"][probe] = {
                    "command": command, "tag": tag, "binder_reply": reply,
                    "output": "\n".join(lines),
                }
                if not lines:
                    raise RuntimeError(f"No new log output for {probe}; Binder return is not success")
                print(probe + ": " + " | ".join(lines))
            report["conclusion"] = classify(report["probes"])
            if not report["conclusion"]["restricted_diagnostic_uid0_verified"]:
                raise RuntimeError("Diagnostic UID 0 in the expected SELinux domain was not verified")
        else:
            report["conclusion"] = {"preflight_only": True, "root_verified_by_this_run": False}
            print("Preflight only. Add --diagnostic to run the fixed short-lived checks.")
        report["after"] = {"shell_identity": adb("shell", "id"), "selinux": adb("shell", "getenforce")}
        report["status"] = "completed"
        return 0
    except (RuntimeError, subprocess.TimeoutExpired, OSError) as exc:
        report["status"] = "incomplete"
        report["error"] = str(exc)
        print(str(exc), file=sys.stderr)
        return 2
    finally:
        if args.output:
            (args.output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    sys.exit(main())

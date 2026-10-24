import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("verify_tv", Path(__file__).resolve().parents[1] / "scripts/verify_tv.py")
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)


class VerificationBoundaries(unittest.TestCase):
    def test_all_commands_fit_property_limit(self):
        for name in verify.PROBES:
            self.assertLessEqual(len(verify.make_command(name, "TVR012abc0").encode()), 91)

    def test_mismatched_build_stops(self):
        props = dict(verify.EXPECTED)
        self.assertTrue(verify.matching_build(props))
        props["ro.build.fingerprint"] += "-different"
        self.assertFalse(verify.matching_build(props))

    def test_binder_reply_is_not_root_evidence(self):
        data = {"identity": {"output": "Result: Parcel(00000000)"},
                "context": {"output": "u:r:misysdiagnose:s0"}}
        self.assertFalse(verify.classify(data)["restricted_diagnostic_uid0_verified"])

    def test_uid_zero_never_claims_full_root_or_backup(self):
        data = {"identity": {"output": "uid=0(root) gid=0(root)"},
                "context": {"output": "u:r:misysdiagnose:s0"}}
        result = verify.classify(data)
        self.assertTrue(result["restricted_diagnostic_uid0_verified"])
        self.assertFalse(result["full_temporary_root_verified"])
        self.assertFalse(result["partition_backup_completed"])

    def test_wrong_context_is_not_expected_success(self):
        data = {"identity": {"output": "uid=0(root)"}, "context": {"output": "u:r:shell:s0"}}
        self.assertFalse(verify.classify(data)["restricted_diagnostic_uid0_verified"])

    def test_header_alone_is_no_log_result(self):
        self.assertEqual(verify.log_lines("--------- beginning of main\n\n"), [])


if __name__ == "__main__":
    unittest.main()

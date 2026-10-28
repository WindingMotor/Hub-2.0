"""Test snapshot isolation, config checks, archive verification, and launch wiring."""

import contextlib
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

SPEC = importlib.util.spec_from_file_location("simulation_run", Path(__file__).resolve().parents[1] / "run.py")
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)
REAL_PROJECT = runner.PROJECT
BASE_CONFIG = runner.read_config(Path(__file__).resolve().parents[1] / "config.json")
BOOT_SPEC = importlib.util.spec_from_file_location(
    "simulation_bootstrap", Path(__file__).resolve().parents[1] / "launch_kipi.py")
bootstrap = importlib.util.module_from_spec(BOOT_SPEC)
BOOT_SPEC.loader.exec_module(bootstrap)


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="hub simulation test ")
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name)
        self.here = self.project / "simulation"
        self.here.mkdir()
        self.board = self.project / BASE_CONFIG["board"]
        self.board.write_bytes((REAL_PROJECT / BASE_CONFIG["board"]).read_bytes())
        self.original = runner.digest(self.board)
        self.config = copy.deepcopy(BASE_CONFIG)
        self.config["copy_patterns"] = ["*.kicad_pcb"]
        self.config_path = self.here / "config.json"
        self.config_path.write_text(json.dumps(self.config))
        for name, value in (("HERE", self.here), ("PROJECT", self.project)):
            patcher = patch.object(runner, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def prepare(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return runner.snapshot(self.config, self.config_path)

    def test_snapshot_isolation_and_repeated_runs(self):
        first, second = self.prepare(), self.prepare()
        self.assertNotEqual(first.parent, second.parent)
        self.assertEqual(first.read_bytes(), self.board.read_bytes())
        setup = first.with_name(first.stem + ".kipi-setup.yml")
        data = json.loads(setup.read_text().split("\n", 1)[1])
        self.assertEqual(data["loads"], self.config["setup"]["loads"])
        model = json.loads(runner.source_path(first).read_text())
        self.assertEqual(model["solder_reinforcement"], self.config["solder_reinforcement"])
        self.assertEqual(model["fabrication"], self.config["fabrication"])
        manifest = json.loads((first.parent / "manifest.json").read_text())
        self.assertEqual(manifest["sha256"][first.name], self.original)
        setup.write_text("edited in KiPI")
        first.write_text("edited snapshot")
        self.assertEqual(runner.digest(self.board), self.original)
        self.assertEqual(runner.digest(second), self.original)

    def test_bad_terminal_does_not_leave_partial_snapshot(self):
        self.config["setup"]["loads"][0]["supply"]["pins"] = ["99999"]
        with self.assertRaisesRegex(ValueError, "Terminal does not match"):
            self.prepare()
        self.assertEqual(list((self.here / "runs").iterdir()), [])

    def test_nonfinite_and_negative_current_rejected(self):
        for value in (float("nan"), float("inf"), -1, True):
            self.config["setup"]["loads"][0]["current"] = value
            with self.assertRaises(ValueError):
                self.prepare()

    def test_invalid_solder_net_does_not_leave_partial_snapshot(self):
        self.config["solder_reinforcement"]["regions"][0]["nets"] = ["typo"]
        with self.assertRaisesRegex(ValueError, "Solder net"):
            self.prepare()
        self.assertEqual(list((self.here / "runs").iterdir()), [])

    def test_duplicate_config_keys_rejected(self):
        self.config_path.write_text('{"config_version": 1, "config_version": 1}')
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            runner.read_config(self.config_path)

    def test_inheritance_merges_objects_replaces_arrays_and_preserves_base(self):
        child = self.here / "case.json"
        child.write_text(json.dumps({"extends": "config.json", "setup": {"loads": []},
                                     "solder_reinforcement": {"enabled": False}}))
        loaded = runner.read_config(child)
        self.assertEqual(loaded["setup"]["loads"], [])
        self.assertEqual(loaded["setup"]["vrms"], self.config["setup"]["vrms"])
        self.assertFalse(loaded["solder_reinforcement"]["enabled"])
        self.assertEqual(loaded["solder_reinforcement"]["regions"],
                         self.config["solder_reinforcement"]["regions"])
        self.assertTrue(runner.read_config(self.config_path)["solder_reinforcement"]["enabled"])
        loaded["setup"]["vrms"][0]["voltage"] = 99
        self.assertEqual(runner.read_config(self.config_path)["setup"]["vrms"][0]["voltage"], 12)

    def test_circular_config_inheritance_rejected(self):
        self.config_path.write_text('{"extends": "config.json"}')
        with self.assertRaisesRegex(ValueError, "Circular"):
            runner.read_config(self.config_path)

    def test_moved_presets_keep_operating_case_and_legacy_paths(self):
        # Real presets resolve against the real config, independent of temporary snapshots.
        with patch.object(runner, "HERE", Path(__file__).resolve().parents[1]):
            normal = runner.read_config(runner.HERE / "config.json")
            without_solder = runner.read_config(runner.HERE / "solder-disabled.json")
            self.assertFalse(without_solder["solder_reinforcement"]["enabled"])
            without_solder["solder_reinforcement"]["enabled"] = True
            self.assertEqual(normal, without_solder)
            copper = runner.read_config(runner.HERE / "cases" / "all-loads.json")
            self.assertFalse(copper["solder_reinforcement"]["enabled"])
            self.assertEqual(copper["component_heat"], [])
            self.assertEqual(copper["connectors"], [])
            self.assertTrue(all(link["resistance"] == 0 for link in copper["setup"]["links"]))

    def test_stackup_mismatch_rejected(self):
        self.config["stackup_source"] = "explicit"
        self.config["setup"]["stackup"] = {"copper_mm": {"F.Cu": .035, "B.Cu": .035},
                                             "dielectric_mm": [1.53]}
        with self.assertRaisesRegex(ValueError, "stackup does not match"):
            self.prepare()

    def test_launch_uses_snapshot_and_local_environment(self):
        fake_kipi = self.here / "KiPI path with spaces"
        with patch.object(runner, "fetch_kipi", return_value=fake_kipi), \
                patch.object(runner.subprocess, "call", return_value=0) as launch, \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(runner.main([]), 0)
        command = launch.call_args.args[0]
        self.assertEqual(command[1], str(self.here / "launch_kipi.py"))
        self.assertEqual(command[2], str(fake_kipi))
        self.assertNotEqual(Path(command[3]), self.board)
        self.assertTrue(Path(command[3]).is_file())
        self.assertEqual(launch.call_args.kwargs["env"]["KIPI_HOST"], "standalone")
        self.assertEqual(launch.call_args.kwargs["env"]["KIPI_HOME"], str(self.here / ".runtime"))

    def test_archive_checksum_and_cache(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w") as zipped:
            zipped.writestr(f"KiPI-{runner.KIPI_COMMIT}/kipi_launcher.py", "# fixture")
        payload = archive.getvalue()
        with patch.object(runner.urllib.request, "urlopen", return_value=io.BytesIO(payload)), \
                contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                runner.fetch_kipi()
        with patch.object(runner, "KIPI_SHA256", hashlib.sha256(payload).hexdigest()), \
                patch.object(runner.urllib.request, "urlopen", return_value=io.BytesIO(payload)), \
                contextlib.redirect_stdout(io.StringIO()):
            installed = runner.fetch_kipi()
        with patch.object(runner.urllib.request, "urlopen", side_effect=AssertionError("network")):
            self.assertEqual(runner.fetch_kipi(), installed)

    def test_dependency_plan_skips_network_resolution(self):
        deps = Mock()
        plan = Mock(pardiso=["optional solver"])
        deps.manifest_plan.return_value = plan
        self.assertIs(bootstrap.dependency_plan(deps, Path("requirements.txt"), False), plan)
        self.assertEqual(plan.pardiso, [])
        deps.live_plan.assert_not_called()
        deps.resolve.assert_not_called()
        deps.manifest_plan.return_value = None
        bootstrap.dependency_plan(deps, Path("requirements.txt"), True)
        deps.names_plan.assert_called_once()
        deps.resolve.assert_not_called()


if __name__ == "__main__":
    unittest.main()

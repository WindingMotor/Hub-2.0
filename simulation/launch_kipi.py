"""Start pinned KiPI without its blocking network-based download-size estimate.

The original Tk setup window stops processing events while make_plan() runs pip
and queries download sizes. Use the bundled estimate (or package names) instead;
the actual installer still resolves and installs requirements normally.
"""

from pathlib import Path
import os
import subprocess
import sys

from component_heat import source_path


def dependency_plan(deps, requirements, offer_pardiso, key=None):
    plan = deps.manifest_plan(key or deps.platform_key())
    if plan is None:
        plan = deps.names_plan(requirements, "Live download-size estimate skipped")
    else:
        plan.note = "Bundled estimate; actual package versions and sizes may differ"
    if not offer_pardiso:
        plan.pardiso = []
    return plan


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2:
        raise ValueError("Expected KiPI directory and board path")
    kipi, board = map(lambda value: Path(value).resolve(), args)
    sys.path.insert(0, str(kipi))
    from kipi.launcher import deps
    from kipi.launcher import main as launcher, paths

    deps.make_plan = lambda python, requirements, offer_pardiso, key=None: dependency_plan(
        deps, requirements, offer_pardiso, key)
    original_launch = launcher.launch

    def launch_application(env, board_file, windowed):
        if not board_file or not source_path(board_file).is_file():
            return original_launch(env, board_file, windowed)
        environment = os.environ.copy()
        environment["KIPI_HOST"] = "standalone"
        environment.pop("KICAD_API_SOCKET", None)
        return subprocess.call([str(paths.env_python(env)),
                                str(Path(__file__).with_name("component_heat.py")),
                                str(kipi), str(board_file)], env=environment)

    launcher.launch = launch_application
    print("Dependency setup uses the terminal; download-size estimation is skipped.", flush=True)
    return launcher.main(["--console", str(board)], windowed=False)


if __name__ == "__main__":
    sys.exit(main())

import copy
import os
import shutil
from os import environ
from pathlib import Path

from build_python_instance_base import BuildPythonInstanceBase
from wheel_builder_utils import (
    _remove_tree,
)


class LinuxBuildPythonInstance(BuildPythonInstanceBase):

    def clone(self):
        # Pattern for generating a deep copy of the current object state as a new build instance
        cls = self.__class__
        new = cls.__new__(cls)
        new.__dict__ = copy.deepcopy(self.__dict__)
        return new

    def get_pixi_environment_name(self):
        # The pixi environment name is the same as the manylinux version
        # and is related to the environment setups defined in pixi.toml
        # in the root of this git directory that contains these scripts.
        return self.platform_env

    def prepare_build_env(self) -> None:
        # #############################################
        # ### Setup build tools
        self.package_env_config["USE_TBB"] = "ON"
        self.package_env_config["TBB_DIR"] = (
            self.build_dir_root / "build" / "oneTBB-prefix" / "lib" / "cmake" / "TBB"
        )

        # The interpreter is provided; ensure basic tools are available
        self.venv_paths()
        self.update_venv_itk_build_configurations()
        if self.package_env_config["ARCH"] == "x64":
            target_triple = "x86_64-linux-gnu"
        elif self.package_env_config["ARCH"] in ("aarch64", "arm64"):
            target_triple = "aarch64-linux-gnu"
        elif self.package_env_config["ARCH"] == "x86":
            target_triple = "i686-linux-gnu"
        else:
            target_triple = f"{self.package_env_config['ARCH']}-linux-gnu"

        target_arch = self.package_env_config["ARCH"]

        self.cmake_compiler_configurations.set(
            "CMAKE_CXX_COMPILER_TARGET:STRING", target_triple
        )

        # build will be here is downloaded
        itk_binary_build_name: Path = (
            self.build_dir_root
            / "build"
            / f"ITK-{self.platform_env}-{self.get_pixi_environment_name()}_{target_arch}"
        )

        self.cmake_itk_source_build_configurations.set(
            "ITK_BINARY_DIR:PATH", itk_binary_build_name.as_posix()
        )

        # Keep values consistent with prior quoting behavior
        # self.cmake_compiler_configurations.set("CMAKE_CXX_FLAGS:STRING", "-O3 -DNDEBUG")
        # self.cmake_compiler_configurations.set("CMAKE_C_FLAGS:STRING", "-O3 -DNDEBUG")

    def post_build_fixup(self) -> None:
        manylinux_ver: str | None = self.package_env_config.get(
            "MANYLINUX_VERSION", None
        )
        if manylinux_ver:
            # Repair all produced wheels with auditwheel for packages with so elements (starts with itk_)
            whl = None
            # cp39-cp39-linux itk_segmentation-6.0.0b2-cp39-cp39-linux_x86_64.whl
            # Extract Python version from platform_env
            if "-" in self.platform_env:
                # in manylinux case, platform env is manylinux-cp310, for example, don't want anything before '-'
                py_version = self.platform_env.split("-")[-1]
            else:
                py_version = self.platform_env
            cp_prefix: str = py_version.replace("py", "cp").replace(".", "")
            binary_wheel_glob_pattern: str = f"itk_*-*{cp_prefix}*-linux_*.whl"
            dist_path: Path = self.build_dir_root / "dist"
            for whl in dist_path.glob(binary_wheel_glob_pattern):
                if whl.name.startswith("itk-"):
                    print(
                        f"Skipping the itk-meta wheel that has nothing to fixup {whl}"
                    )
                    continue
                self.fixup_wheel(str(whl))
            del whl
            # Retag meta-wheel: Special handling for the itk meta wheel to adjust tag
            # auditwheel does not process this "metawheel" correctly since it does not
            # have any native SO's.
            meta_wheel_glob_pattern: str = f"itk-*-*{cp_prefix}*-linux_*.whl"
            for metawhl in dist_path.glob(meta_wheel_glob_pattern):
                # Unpack, edit WHEEL tag, repack
                metawheel_dir = self.build_dir_root / "metawheel"
                metawheel_dir.mkdir(parents=True, exist_ok=True)
                self.echo_check_call(
                    [
                        self.package_env_config["PYTHON_EXECUTABLE"],
                        "-m",
                        "wheel",
                        "unpack",
                        "--dest",
                        str(metawheel_dir),
                        str(metawhl),
                    ]
                )
                # Find unpacked dir
                unpacked_dirs = list(metawheel_dir.glob("itk-*/itk*.dist-info/WHEEL"))
                for wheel_file in unpacked_dirs:
                    content = wheel_file.read_text(encoding="utf-8").splitlines()
                    base = metawhl.name
                    if len(manylinux_ver) > 0:
                        base = metawhl.name.replace(
                            "linux", f"manylinux{manylinux_ver}"
                        )
                    tag = Path(base).stem
                    new = []
                    for line in content:
                        if line.startswith("Tag: "):
                            new.append(f"Tag: {tag}")
                        else:
                            new.append(line)
                    wheel_file.write_text("\n".join(new) + "\n", encoding="utf-8")
                for fixed_dir in metawheel_dir.glob("itk-*"):
                    metawheel_dist = self.build_dir_root / "metawheel-dist"
                    metawheel_dist.mkdir(parents=True, exist_ok=True)
                    self.echo_check_call(
                        [
                            self.package_env_config["PYTHON_EXECUTABLE"],
                            "-m",
                            "wheel",
                            "pack",
                            "--dest",
                            str(metawheel_dist),
                            str(fixed_dir),
                        ]
                    )
                # Move and clean
                for new_whl in metawheel_dist.glob("*.whl"):
                    shutil.move(
                        str(new_whl),
                        str((self.build_dir_root / "dist") / new_whl.name),
                    )
                # Remove old and temp
                try:
                    metawhl.unlink()
                except OSError:
                    pass
                _remove_tree(metawheel_dir)
                _remove_tree(metawheel_dist)

    def final_import_test(self) -> None:
        self._final_import_test_fn(self.platform_env, Path(self.dist_dir))

    def fixup_wheel(
        self, filepath, lib_paths: str = "", remote_module_wheel: bool = False
    ) -> None:
        # Use auditwheel to repair wheels and set manylinux tags
        manylinux_ver = self.package_env_config.get("MANYLINUX_VERSION", "")
        if len(manylinux_ver) > 1:
            plat = None
            if self.package_env_config["ARCH"] == "x64" and manylinux_ver:
                plat = f"manylinux{manylinux_ver}_x86_64"
            cmd = [
                self.package_env_config["PYTHON_EXECUTABLE"],
                "-m",
                "auditwheel",
                "repair",
            ]
            if plat:
                cmd += ["--plat", plat]
            cmd += [
                str(filepath),
                "-w",
                (
                    str(self.module_source_dir / "dist")
                    if remote_module_wheel
                    else str(self.build_dir_root / "dist")
                ),
            ]
            # Provide LD_LIBRARY_PATH for oneTBB and common system paths
            extra_lib = str(
                self.package_env_config["IPP_SUPERBUILD_BINARY_DIR"].parent
                / "oneTBB-prefix"
                / "lib"
            )
            env = dict(self.package_env_config)
            env["LD_LIBRARY_PATH"] = ":".join(
                [
                    env.get("LD_LIBRARY_PATH", ""),
                    extra_lib,
                    "/usr/lib64",
                    "/usr/lib",
                ]
            )
            print(f'RUNNING WITH PATH {os.environ["PATH"]}')
            env["PATH"] = os.environ["PATH"]
            self.echo_check_call(cmd, env=env)

            # Remove the original linux_*.whl after successful repair
            filepath_obj = Path(filepath)
            if (
                filepath_obj.exists()
                and "-linux_" in filepath_obj.name
                and filepath_obj.suffix == ".whl"
            ):
                print(
                    f"Removing original linux wheel after repair: {filepath_obj.name}"
                )
                try:
                    _remove_tree(filepath_obj)
                except OSError as e:
                    print(f"Warning: Could not remove {filepath_obj.name}: {e}")
        else:
            print(
                "Building outside of manylinux environment does not require wheel fixups."
            )
        return

    def post_build_cleanup(self) -> None:
        """Clean build artifacts

        Actions (leaving dist/ intact):
        - remove oneTBB-prefix (symlink or dir)
        - remove ITKPythonPackage/, tools/, _skbuild/, build/
        - remove top-level *.egg-info
        - remove ITK-* build tree and tarballs
        - if ITK_MODULE_PREQ is set ("org/name@ref:org2/name2@ref2"), remove cloned module dirs
        """
        base = Path(self.package_env_config["IPP_SOURCE_DIR"])

        # Helper to remove arbitrary paths (files/dirs) quietly
        def rm(tree_path: Path):
            try:
                _remove_tree(tree_path)
            except Exception:
                pass

        # 1) unlink oneTBB-prefix if it's a symlink or file
        tbb_prefix_dir = base / "oneTBB-prefix"
        try:
            if tbb_prefix_dir.is_symlink() or tbb_prefix_dir.is_file():
                tbb_prefix_dir.unlink(missing_ok=True)  # type: ignore[arg-type]
            elif tbb_prefix_dir.exists():
                # If it is a directory (not expected), remove tree
                rm(tbb_prefix_dir)
        except Exception:
            pass

        # 2) standard build directories
        for rel in ("ITKPythonPackage", "tools", "_skbuild", "build"):
            rm(base / rel)

        # 3) egg-info folders at top-level
        for p in base.glob("*.egg-info"):
            rm(p)

        # 4) ITK build tree and tarballs
        target_arch = self.package_env_config["ARCH"]
        for p in base.glob(f"ITK-*-{self.package_env_config}_{target_arch}"):
            rm(p)

        # Tarballs
        for p in base.glob(f"ITKPythonBuilds-{self.package_env_config}*.tar.zst"):
            rm(p)

        # 5) Optional module prerequisites cleanup (ITK_MODULE_PREQ)
        # Format: "InsightSoftwareConsortium/ITKModuleA@v1.0:Kitware/ITKModuleB@sha" -> remove repo names
        itk_preq = self.package_env_config.get("ITK_MODULE_PREQ") or environ.get(
            "ITK_MODULE_PREQ", ""
        )
        if itk_preq:
            for entry in itk_preq.split(":"):
                entry = entry.strip()
                if not entry:
                    continue
                try:
                    module_name = entry.split("@", 1)[0].split("/", 1)[1]
                except Exception:
                    continue
                rm(base / module_name)

    def build_tarball(self):
        self.create_posix_tarball()

    def venv_paths(self) -> None:
        """Resolve virtualenv tool paths.
        platform_env may be a name under IPP_SOURCE_DIR/venvs or an absolute/relative path to a venv.
        """
        primary_python_base_dir = Path(
            self.package_env_config["PYTHON_EXECUTABLE"]
        ).parent.parent
        # if True:
        #     self._pip_uninstall_itk_wildcard(self.package_env_config["PYTHON_EXECUTABLE"])
        (
            python_executable,
            python_include_dir,
            python_library,
            venv_bin_path,
            venv_base_dir,
        ) = self.find_unix_exectable_paths(primary_python_base_dir)
        self.venv_info_dict = {
            "python_executable": python_executable,
            "python_include_dir": python_include_dir,
            "python_library": python_library,
            "venv_bin_path": venv_bin_path,
            "venv_base_dir": venv_base_dir,
            "python_root_dir": primary_python_base_dir,
        }

    def discover_python_venvs(
        self, platform_os_name: str, platform_architechure: str
    ) -> list[str]:
        names = []

        # Discover virtualenvs under project 'venvs' folder
        def _discover_ipp_venvs() -> list[str]:
            venvs_dir = self.build_dir_root / "venvs"
            if not venvs_dir.exists():
                return []
            names.extend([p.name for p in venvs_dir.iterdir() if p.is_dir()])
            # Sort for stable order
            return sorted(names)

        # Discover available manylinux CPython installs under /opt/python
        def _discover_manylinuxlocal_pythons() -> list[str]:
            base = Path("/opt/python")
            if not base.exists():
                return []
            names.extend([p.name for p in base.iterdir() if p.is_dir()])
            return sorted(names)

        default_platform_envs = (
            _discover_manylinuxlocal_pythons() + _discover_ipp_venvs()
        )

        return default_platform_envs

    def _final_import_test_fn(self, platform_env, param):
        pass

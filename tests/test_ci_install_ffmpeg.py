"""The CI ffmpeg install falls back to apt whenever the pinned static build can't be used."""

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "install-ffmpeg.sh"

FAKE_TOOL = """#!/bin/sh
echo "$(basename "$0") version {label}"
"""


def write_tool(path: Path, label: str) -> None:
    path.write_text(FAKE_TOOL.format(label=label))
    path.chmod(0o755)


@pytest.fixture
def stubs(tmp_path: Path) -> Path:
    """A bin folder with stand-ins for sudo and apt-get; `apt-get install` adds fake tools."""
    bin_dir = tmp_path / "stubs"
    bin_dir.mkdir()
    (bin_dir / "sudo").write_text('#!/bin/sh\nexec "$@"\n')
    (bin_dir / "apt-get").write_text(
        "#!/bin/sh\n"
        f'echo "apt-get $*" >> "{tmp_path}/apt.log"\n'
        'case " $* " in *" install "*)\n'
        + "".join(
            f"  printf '%s\\n' '#!/bin/sh' 'echo \"{t} version from-apt\"' > \"{bin_dir}/{t}\"\n"
            f'  chmod +x "{bin_dir}/{t}"\n'
            for t in ("ffmpeg", "ffprobe")
        )
        + "esac\n"
    )
    for name in ("sudo", "apt-get"):
        (bin_dir / name).chmod(0o755)
    return bin_dir


def run_script(tmp_path: Path, stubs: Path, base_url: str) -> subprocess.CompletedProcess[str]:
    runner_temp = tmp_path / "runner"
    runner_temp.mkdir()
    env = {
        "PATH": f"{stubs}:/usr/bin:/bin",
        "RUNNER_TEMP": str(runner_temp),
        "GITHUB_PATH": str(tmp_path / "github_path"),
        "FFMPEG_BASE_URL": base_url,
        "HOME": os.environ.get("HOME", str(tmp_path)),
    }
    return subprocess.run(
        ["bash", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=60
    )


def test_missing_download_falls_back_to_apt(tmp_path: Path, stubs: Path) -> None:
    result = run_script(tmp_path, stubs, (tmp_path / "nothing-here").as_uri())

    assert result.returncode == 0, result.stderr
    assert "falling back to apt" in result.stdout
    assert "Installed ffmpeg from apt" in result.stdout
    assert "ffmpeg version from-apt" in result.stdout
    assert "ffprobe version from-apt" in result.stdout
    assert "--no-install-recommends ffmpeg" in (tmp_path / "apt.log").read_text()
    assert not (tmp_path / "github_path").exists()


def test_build_with_wrong_digest_is_never_run(tmp_path: Path, stubs: Path) -> None:
    release = tmp_path / "release"
    release.mkdir()
    marker = tmp_path / "ran"
    staged = tmp_path / "staged" / "ffmpeg" / "bin"
    staged.mkdir(parents=True)
    for name in ("ffmpeg", "ffprobe"):
        (staged / name).write_text(f"#!/bin/sh\ntouch {marker}\n")
        (staged / name).chmod(0o755)
    archive = release / "ffmpeg-n8.1.3-9-g29e619e767-linux64-gpl-8.1.tar.xz"
    subprocess.run(
        ["tar", "-cJf", str(archive), "-C", str(tmp_path / "staged"), "ffmpeg"], check=True
    )

    result = run_script(tmp_path, stubs, release.as_uri())

    assert result.returncode == 0, result.stderr
    assert "Installed ffmpeg from apt" in result.stdout
    assert "ffmpeg version from-apt" in result.stdout
    assert not marker.exists()
    assert not (tmp_path / "github_path").exists()


def test_apt_failure_fails_the_step(tmp_path: Path, stubs: Path) -> None:
    (stubs / "apt-get").write_text("#!/bin/sh\nexit 100\n")

    result = run_script(tmp_path, stubs, (tmp_path / "nothing-here").as_uri())

    assert result.returncode != 0
    assert "Installed ffmpeg from apt" not in result.stdout

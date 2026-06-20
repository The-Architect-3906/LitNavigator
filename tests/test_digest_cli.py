import subprocess, sys


def test_digest_demo_cli_runs_offline():
    out = subprocess.run([sys.executable, "-m", "litnav.app", "digest-demo"],
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert "edge_accuracy" in out.stdout.lower()

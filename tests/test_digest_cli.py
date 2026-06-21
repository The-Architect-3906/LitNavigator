import subprocess, sys


def test_digest_demo_cli_runs_offline_deterministically():
    """digest-demo must FORCE provider=none and produce the deterministic fixture result,
    regardless of any LITNAV_LLM_PROVIDER in the environment/.env."""
    import os
    env = dict(os.environ, LITNAV_LLM_PROVIDER="openai")  # even if env says live, demo must force none
    out = subprocess.run([sys.executable, "-m", "litnav.app", "digest-demo"],
                         capture_output=True, text=True, env=env)
    assert out.returncode == 0, out.stderr
    # deterministic offline result for data/seed/digest_sources_fixture.json:
    assert "3 concepts" in out.stdout
    assert "3 edges" in out.stdout
    assert "1 flagged" in out.stdout
    assert "edge_accuracy=0.5" in out.stdout

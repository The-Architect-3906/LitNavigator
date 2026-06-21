from litnav.evaluation import verify_artifact


def test_verify_artifact_offline_gate():
    assert verify_artifact.main() == 0

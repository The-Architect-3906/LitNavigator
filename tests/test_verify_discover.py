from litnav.evaluation.verify_discover import main


def test_verify_discover_offline_gate():
    assert main() == 0

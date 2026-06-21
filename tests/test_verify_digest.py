from litnav.evaluation.verify_digest import main


def test_verify_digest_gate_passes():
    assert main() == 0

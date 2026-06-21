from litnav.evaluation.verify_teach_assess import main


def test_verify_teach_assess_offline_gate():
    assert main() == 0

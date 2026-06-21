"""Run the multi-turn mastery probe against the LIVE provider (loads .env).

Used for eval-gated loop iterations whose effect is only visible with real LLM grading (e.g. R6
partial-credit grading). Prints the same metric dict as run_probe.

    python -m litnav.eval.probe_live --learner partial_then_full
"""
from __future__ import annotations


def main() -> None:
    import argparse
    from litnav.config import load_dotenv
    load_dotenv()  # LITNAV_LLM_PROVIDER=openai etc. → probe grades live

    from litnav.eval import mastery_probe as mp

    ap = argparse.ArgumentParser()
    ap.add_argument("--learner", default="partial_then_full",
                    choices=["partial_then_full", "lost_then_recover", "always_correct"])
    args = ap.parse_args()

    learner = getattr(mp, args.learner)
    result = mp.run_probe(learner=learner)
    print(f"learner={args.learner}  {result}")


if __name__ == "__main__":
    main()

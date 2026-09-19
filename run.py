"""Main CLI entry point for the Clinical Study Surveillance Platform (ATLAS -> MONITOR -> WATCH)."""
import os
import sys
import argparse
import json
import uvicorn
from stage1.atlas import Atlas
from stage2.crew import ReviewCrew
from stage3.watch import StudyWatch


def main():
    parser = argparse.ArgumentParser(
        description="Study Sentinel — Clinical Study Surveillance Platform (ATLAS -> MONITOR -> WATCH)"
    )
    parser.add_argument(
        "--mode",
        choices=["full", "cut", "explain", "ui", "test"],
        default="full",
        help="Execution mode: full (all 12 cuts), cut (single cut), explain (trace lookup), ui (launch web app), test (run pytest)",
    )
    parser.add_argument(
        "--data_dir",
        default=os.path.join(os.path.dirname(__file__), "hackathon-data", "hackathon-data"),
        help="Path to trial data directory",
    )
    parser.add_argument("--cut", type=int, default=12, help="Specific cut number for --mode cut")
    parser.add_argument("--explain", dest="decision_id", type=str, help="Decision ID to explain")
    parser.add_argument("--port", type=int, default=8000, help="Port for UI server")

    args = parser.parse_args()

    # Mode: Test
    if args.mode == "test":
        import pytest
        sys.exit(pytest.main(["-v", "tests"]))

    # Initialize Platform Components
    atlas = Atlas(data_dir=args.data_dir)
    crew = ReviewCrew(atlas=atlas)
    watch = StudyWatch(data_dir=args.data_dir, crew=crew, max_budget_seconds=300.0)

    # Mode: Full 12-Cut Run
    if args.mode == "full":
        print("=" * 70)
        print("  STUDY SENTINEL SURVEILLANCE PLATFORM — 12-CUT UNATTENDED RUN")
        print("=" * 70)
        print(f"Data Source Directory: {args.data_dir}")
        print("Executing cuts 1 -> 12...\n")

        summary = watch.run_period(cuts=range(1, 13))

        print("\n" + "=" * 70)
        print("  12-CUT SURVEILLANCE SUMMARY")
        print("=" * 70)
        print(f"Total Cuts Evaluated:        {len(summary['cuts_evaluated'])}")
        print(f"Total Audit Trace Entries:   {summary['total_trace_entries']}")
        print(f"Retroactive Corrections:     {summary['applied_corrections']}")
        print(f"Adversarial Interceptions:   {len(summary['adversarial_alerts'])}")
        print(f"Budget Status:               {summary['budget_status']['tier']} ({summary['budget_status']['elapsed_seconds']}s elapsed)")
        print(f"Report Generated:            {summary['report_path']}")
        print(f"Trace Exported:              {summary['trace_path']}")
        print("=" * 70)

        # Print sample explanation
        all_entries = watch.trace.get_all()
        if all_entries:
            sample_dec = all_entries[-1].decision_id
            exp = watch.explain(sample_dec)
            print(f"\n[Trace Verification Sample] explain('{sample_dec}'):")
            print(f"  What: {exp.what}")
            print(f"  Why:  {exp.why}")
            print(f"  Consistent With Trace: {exp.consistent_with_trace}")

    # Mode: Single Cut
    elif args.mode == "cut":
        print(f"Executing Single Cycle for Cut {args.cut}...")
        pv = atlas.data_loader.get_protocol_version_for_cut(args.cut)
        result = crew.run_cycle(cut=args.cut, protocol_version=pv)
        print(json.dumps(result.summary, indent=2))

    # Mode: Explain
    elif args.mode == "explain":
        if not args.decision_id:
            print("Error: --explain <DECISION_ID> is required in explain mode.")
            sys.exit(1)
        watch.run_period(cuts=range(1, 13))
        exp = watch.explain(args.decision_id)
        print(json.dumps(exp.model_dump(), indent=2))

    # Mode: UI Web Server
    elif args.mode == "ui":
        print(f"Launching Study Sentinel Web Platform on http://localhost:{args.port}...")
        uvicorn.run("ui.server:app", host="0.0.0.0", port=args.port, reload=False)


if __name__ == "__main__":
    main()

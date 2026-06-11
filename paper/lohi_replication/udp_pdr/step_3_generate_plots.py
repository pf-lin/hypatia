import os
import subprocess
import sys

sys.path.append(os.path.join(os.path.dirname(__file__)))
from dynamic_run_list import build_arg_parser, validate_focus_pair_arguments


def main():
    parser = build_arg_parser("Analyze and plot UDP/PDR packet delivery results.")
    args, passthrough = parser.parse_known_args()
    validate_focus_pair_arguments(parser, args)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_cmd = [
        sys.executable,
    ]
    common_args = sys.argv[1:]

    print("[Step 3.1] Analyzing packet delivery...")
    subprocess.check_call(base_cmd + [os.path.join(script_dir, "analyze_packet_delivery.py")] + common_args)

    print("\n[Step 3.2] Plotting packet delivery comparison...")
    subprocess.check_call(base_cmd + [os.path.join(script_dir, "plot_packet_delivery_comparison.py")] + common_args)

    if args.enable_rtt_analysis:
        print("\n[Step 3.3] Generating estimated RTT and route outputs...")
        try:
            subprocess.check_call(
                base_cmd
                + [os.path.join(script_dir, "udp_rtt_analysis.py")]
                + common_args
            )
        except subprocess.CalledProcessError as exc:
            print(
                "Warning: RTT analysis failed with exit code %d; existing "
                "packet-delivery outputs remain available." % exc.returncode,
                file=sys.stderr,
            )

    print("\nStep 3 complete.")


if __name__ == "__main__":
    main()

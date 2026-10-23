# main method to execute commands

import argparse
from parser import parse_expression, generate_truth_table
from verilog_generator import generate_verilog

if __name__ == "__main__":
    # argparse provides a command-line interface and automatically
    # handles argument validation and help messages
    cli = argparse.ArgumentParser(description="Direct SOP/POS Boolean parser")

    # argument containing expression
    cli.add_argument("expression", help="Boolean SOP or POS expression")

    # optional argument specifying the input format
    # Ex:
    # python parser.py "(A+B)(A'+C)" --form pos
    # if omitted, automatic detection is used
    cli.add_argument(
        "--form",
        choices=["auto", "sop", "pos"],
        default="auto",
        help="Expression format (default: auto)"
    )

    # parse the command-line arguments.
    args = cli.parse_args()

    try:
        # convert the input string into structured terms
        form, terms = parse_expression(args.expression, args.form)

        # evaluate the expression for every input combination
        variables, rows, on_set, off_set = generate_truth_table(terms, form)

        print(f"Form: {form.upper()}")
        print(f"Parsed terms: {terms}")
        print(f"Variables: {variables}")

        # build the header first so the divider always matches its width
        # (works for constant expressions with no variables, too)
        header = " ".join(variables + ["| F"]) if variables else "F"

        print("\nTruth Table:")
        print(header)
        print("-" * len(header))

        for bits, output in rows:
            print(" ".join(list(map(str, bits)) + ["|", str(output)]) if bits else output)

        print("\nON-set:", on_set)
        print("OFF-set:", off_set)

        # Generate structural Verilog.
        source = generate_verilog(terms, form, "boolean_function", "output.v")

        print("Structural Verilog file \"output.v\" generated in current directory")

    except ValueError as exc:
        # cli.error() prints the error message and exits with a nonzero status code
        cli.error(str(exc))

# main method to execute commands
#
# runs the 12 operations on 1 function + writes structural verilog of the min circuit
#
# input:
#   expression in quotes    Ex: "AB' + A'C"   or   "(A+B)(A'+C)"
#   .eqn file               Ex: examples/example1.eqn
#   .json circuit           Ex: examples/full_adder.json
#
# Ex:
#   python3 main.py "AB' + A'C"                     (all 12 operations)
#   python3 main.py "AB' + A'C" --ops 5 7 8         (just those)
#   python3 main.py examples/full_adder.json --output COUT
#   python3 main.py "AB' + A'C" --verilog-form pos  (verilog from min POS)

import argparse
import re
import sys

from parser import parse_expression, generate_truth_table, load_circuit, circuit_truth_table
from minimize import (
    find_prime_implicants,
    find_essential_implicants,
    find_minimum_cover,
    count_literals,
    product_term,
    sum_term,
    sop_expression,
    pos_expression,
    minterm_patterns,
)
from analysis import find_hazards, fix_hazards, describe_hazard, estimate_delay
from verilog_generator import generate_verilog


# all info on 1 function, minimization done once here
# SOP: minimize ON-set  --> implicants of F
# POS: minimize OFF-set --> implicants of F', printed w/ DeMorgan
#      Ex: F' = AC' --> F = (A' + C)
class LogicFunction:
    def __init__(self, name, variables, rows, on_set, off_set, source):
        self.name = name                # Ex: "F"
        self.variables = variables      # Ex: ["A", "B", "C"]
        self.n = len(variables)         # Ex: 3
        self.rows = rows                # Ex: [("000", 0), ("001", 1), ...]
        self.on_set = on_set            # Ex: [1, 3, 4, 5]
        self.off_set = off_set          # Ex: [0, 2, 6, 7]
        self.source = source            # printed at top

        self.sop_primes = find_prime_implicants(on_set, self.n)
        self.sop_essentials = find_essential_implicants(self.sop_primes, on_set)
        self.sop_cover, self.sop_exact = find_minimum_cover(
            self.sop_primes, self.sop_essentials, on_set)

        self.pos_primes = find_prime_implicants(off_set, self.n)
        self.pos_essentials = find_essential_implicants(self.pos_primes, off_set)
        self.pos_cover, self.pos_exact = find_minimum_cover(
            self.pos_primes, self.pos_essentials, off_set)


# typed expression (or from a .eqn file)
def load_expression(expression, form="auto", order=None, name="F"):
    form, terms = parse_expression(expression, form)
    variables, rows, on_set, off_set = generate_truth_table(terms, form, order)
    source = f"{form.upper()} expression: {expression}"
    return LogicFunction(name, variables, rows, on_set, off_set, source)


# .eqn file: 1 equation + optional FORM / INORDER lines
# Ex:
#   # comment
#   FORM    = sop;
#   INORDER = A B C D;
#   F       = A'B'C' + B'CD' + A'BCD' + AB'C';
def load_eqn_file(path):
    form = "auto"
    order = None
    name = None
    expression = None

    with open(path, encoding="utf-8") as file:
        for line in file:
            # drop comments + spaces
            line = line.split("#")[0].strip()
            if line == "":
                continue

            # "NAME = value;" -> 2 halves
            # Ex: "F = AB + C;" --> key "F", value "AB + C"
            match = re.fullmatch(r"(\w+)\s*=\s*(.*?)\s*;?", line)
            if match is None:
                raise ValueError(f"{path}: expected 'NAME = expression;' but got '{line}'")
            key = match.group(1)
            value = match.group(2)

            if key.upper() == "FORM":
                form = value.lower()
            elif key.upper() == "INORDER":
                order = value.split()
            elif expression is None:
                name = key
                expression = value
            else:
                raise ValueError(f"{path}: only one equation per file is supported")

    if expression is None:
        raise ValueError(f"{path}: no equation found")

    return load_expression(expression, form, order, name)


# .json circuit: simulate gates -> truth table of 1 output
def load_circuit_file(path, output=None):
    circuit = load_circuit(path)
    variables, rows, on_set, off_set, output = circuit_truth_table(circuit, output)

    source = f"circuit {path} ({len(circuit['gates'])} gates), output {output}"
    if len(circuit["outputs"]) > 1:
        source = source + "  (other outputs: choose with --output)"
    return LogicFunction(output, variables, rows, on_set, off_set, source)


# [1, 3, 4, 5] --> "1, 3, 4, 5"
def number_list(numbers):
    text = []
    for number in numbers:
        text.append(str(number))
    return ", ".join(text)


# total literals in a list of implicants
def total_literals(patterns):
    total = 0
    for pattern in patterns:
        total = total + count_literals(pattern)
    return total


# Ex: "Literals: 4 vs 12 canonical --> saved 8 (66.7%)"
def savings_line(canonical, minimized):
    saved = canonical - minimized
    text = f"Literals: {minimized} vs {canonical} canonical --> saved {saved}"
    if canonical > 0:
        text = text + f" ({100 * saved / canonical:.1f}%)"
    return text


# min cover -> parser-style terms for verilog_generator
# SOP pattern: '1' = plain, '0' = complemented
# POS pattern (implicant of F', DeMorgan): '0' = plain, '1' = complemented
# Ex: SOP ["0-1", "10-"] w/ [A, B, C] --> [[("A", False), ("C", True)], [("A", True), ("B", False)]]
def cover_to_terms(cover, variables, is_pos):
    # no terms: SOP -> F = 0, POS -> F = 1
    if len(cover) == 0:
        return [[("CONST", is_pos)]]

    if is_pos:
        plain = "0"
    else:
        plain = "1"

    terms = []
    for pattern in cover:
        term = []
        for position in range(len(pattern)):
            if pattern[position] != "-":
                term.append((variables[position], pattern[position] == plain))

        # term w/ no literals: SOP -> F = 1, POS -> F = 0
        if len(term) == 0:
            return [[("CONST", not is_pos)]]

        terms.append(term)
    return terms


# 1. canonical SOP = OR of all ON-set minterms
def canonical_sop(f):
    print("\n[1] Canonical SOP")
    print(f"  {f.name} = Σm({number_list(f.on_set)})")
    print(f"  {f.name} = {sop_expression(minterm_patterns(f.on_set, f.n), f.variables)}")


# 2. canonical POS = AND of all OFF-set maxterms
def canonical_pos(f):
    print("\n[2] Canonical POS")
    print(f"  {f.name} = ΠM({number_list(f.off_set)})")
    print(f"  {f.name} = {pos_expression(minterm_patterns(f.off_set, f.n), f.variables)}")


# 3. inverse SOP: F' = 1 where F = 0 -> use OFF-set
def inverse_sop(f):
    print("\n[3] Inverse canonical SOP")
    print(f"  {f.name}' = Σm({number_list(f.off_set)})")
    print(f"  {f.name}' = {sop_expression(minterm_patterns(f.off_set, f.n), f.variables)}")


# 4. inverse POS: F' = 0 where F = 1 -> maxterms = ON-set
def inverse_pos(f):
    print("\n[4] Inverse canonical POS")
    print(f"  {f.name}' = ΠM({number_list(f.on_set)})")
    print(f"  {f.name}' = {pos_expression(minterm_patterns(f.on_set, f.n), f.variables)}")


# 5. min SOP + literals saved vs canonical SOP
def minimized_sop(f):
    print("\n[5] Literal-minimized SOP")
    print(f"  {f.name} = {sop_expression(f.sop_cover, f.variables)}")
    print("  " + savings_line(f.n * len(f.on_set), total_literals(f.sop_cover)))
    if not f.sop_exact:
        print("  (large function: greedy choice used, may not be the absolute minimum)")


# 6. min POS + literals saved vs canonical POS
def minimized_pos(f):
    print("\n[6] Literal-minimized POS")
    print(f"  {f.name} = {pos_expression(f.pos_cover, f.variables)}")
    print("  " + savings_line(f.n * len(f.off_set), total_literals(f.pos_cover)))
    if not f.pos_exact:
        print("  (large function: greedy choice used, may not be the absolute minimum)")


# 7-10. counts only
def prime_implicants(f):
    print(f"\n[7] Prime implicants: {len(f.sop_primes)}")


def essential_prime_implicants(f):
    print(f"\n[8] Essential prime implicants: {len(f.sop_essentials)}")


def on_set_minterms(f):
    print(f"\n[9] ON-set minterms: {len(f.on_set)}")


def off_set_maxterms(f):
    print(f"\n[10] OFF-set maxterms: {len(f.off_set)}")


# 11. custom #1: static-1 hazards (min SOP) + static-0 hazards (min POS)
def hazards(f):
    print("\n[11] Custom #1: static hazard detection")

    print(f"  Minimized SOP: {f.name} = {sop_expression(f.sop_cover, f.variables)}")
    found = find_hazards(f.sop_cover, f.on_set, f.n)
    if len(found) == 0:
        print("    No static-1 hazards.")
    else:
        print(f"    {len(found)} static-1 hazard(s), output may glitch 1 -> 0 -> 1 when:")
        for hazard in found:
            print("      " + describe_hazard(hazard, f.variables))
        fixed, added = fix_hazards(f.sop_cover, f.sop_primes, found)
        added_text = []
        for pattern in added:
            added_text.append(product_term(pattern, f.variables))
        print("    Fix: add " + ", ".join(added_text))
        print(f"    Hazard-free SOP: {f.name} = {sop_expression(fixed, f.variables)}")

    print(f"  Minimized POS: {f.name} = {pos_expression(f.pos_cover, f.variables)}")
    found = find_hazards(f.pos_cover, f.off_set, f.n)
    if len(found) == 0:
        print("    No static-0 hazards.")
    else:
        print(f"    {len(found)} static-0 hazard(s), output may glitch 0 -> 1 -> 0 when:")
        for hazard in found:
            print("      " + describe_hazard(hazard, f.variables))
        fixed, added = fix_hazards(f.pos_cover, f.pos_primes, found)
        added_text = []
        for pattern in added:
            added_text.append(sum_term(pattern, f.variables))
        print("    Fix: add " + ", ".join(added_text))
        print(f"    Hazard-free POS: {f.name} = {pos_expression(fixed, f.variables)}")


# 12. custom #2: gates + delay for each version of the circuit
def delay(f):
    print("\n[12] Custom #2: delay estimation")

    hazard_list = find_hazards(f.sop_cover, f.on_set, f.n)
    hazard_free, added = fix_hazards(f.sop_cover, f.sop_primes, hazard_list)

    # (label, terms, is_pos)
    designs = [
        ("Canonical SOP", minterm_patterns(f.on_set, f.n), False),
        ("Minimized SOP", f.sop_cover, False),
        ("Hazard-free SOP", hazard_free, False),
        ("Canonical POS", minterm_patterns(f.off_set, f.n), True),
        ("Minimized POS", f.pos_cover, True),
    ]

    print(f"  {'Implementation':<17}{'gates':>6}{'delay':>8}")
    for label, patterns, is_pos in designs:
        gates, total_delay = estimate_delay(patterns, is_pos)
        print(f"  {label:<17}{gates:>6}{total_delay:>8.1f}")

    print("  (delay in gate delays: NOT, AND and OR = 1 each, edit them in analysis.py)")


# operations in order, list position + 1 = operation #
OPERATIONS = [
    canonical_sop, canonical_pos, inverse_sop, inverse_pos,
    minimized_sop, minimized_pos, prime_implicants, essential_prime_implicants,
    on_set_minterms, off_set_maxterms, hazards, delay,
]


if __name__ == "__main__":
    # so Σ / Π print right on Windows + when saved to a file
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

    # argparse provides a command-line interface and automatically
    # handles argument validation and help messages
    cli = argparse.ArgumentParser(description="EC551 logic synthesis engine")

    # expression, .eqn file or .json circuit
    cli.add_argument("input", help="expression in quotes, a .eqn file, or a .json circuit")

    # optional argument specifying the input format (typed expressions)
    # Ex:
    # python3 main.py "(A+B)(A'+C)" --form pos
    # if omitted, automatic detection is used
    cli.add_argument(
        "--form",
        choices=["auto", "sop", "pos"],
        default="auto",
        help="Expression format (default: auto)"
    )

    # which operations to run, default all 12
    cli.add_argument("--ops", nargs="+", type=int, default=None,
                     help="operation numbers to run, Ex: --ops 5 7 8 (default: all)")

    # which output of a .json circuit
    cli.add_argument("--output", default=None,
                     help="output of a .json circuit to use (default: first)")

    # verilog settings
    cli.add_argument("--verilog-form", choices=["sop", "pos"], default="sop",
                     help="build the verilog from the minimized SOP or POS (default: sop)")
    cli.add_argument("--verilog-file", default="output.v",
                     help="verilog file to write (default: output.v)")

    # parse the command-line arguments
    args = cli.parse_args()

    try:
        # input type from file ending
        if args.input.lower().endswith(".json"):
            f = load_circuit_file(args.input, args.output)
        elif args.output is not None:
            raise ValueError("--output only applies to .json circuit files")
        elif args.input.lower().endswith(".eqn"):
            f = load_eqn_file(args.input)
        else:
            f = load_expression(args.input, args.form)

        # operation numbers to run
        ops = args.ops
        if ops is None:
            ops = list(range(1, 13))
        for number in ops:
            if number < 1 or number > 12:
                raise ValueError(f"Operation {number} does not exist (use 1-12)")

        print(f"Input:     {f.source}")
        print(f"Variables: {', '.join(f.variables)}")

        for number in ops:
            OPERATIONS[number - 1](f)

        # generate structural verilog of the minimized circuit
        if args.verilog_form == "sop":
            terms = cover_to_terms(f.sop_cover, f.variables, False)
        else:
            terms = cover_to_terms(f.pos_cover, f.variables, True)

        generate_verilog(terms, args.verilog_form, "boolean_function",
                         args.verilog_file, f.variables)

        print(f"\nStructural Verilog file \"{args.verilog_file}\" generated "
              f"(minimized {args.verilog_form.upper()})")

    except (ValueError, OSError) as exc:
        # cli.error() prints the error message and exits with a nonzero status code
        cli.error(str(exc))

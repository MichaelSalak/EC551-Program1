# EQN style parser

import re
import argparse
from itertools import product

# convert boolean literal into a tuple containing its name and polarity (complemented or not)
# Ex:
# "A" --> ("A", True)
# "B'" --> ("B", False)
def parse_literal(token):
    # check whether string matches the format of:
    # [A-Za-z] : exactly one uppercase or lowercase letter
    # '? : an optional apostrophe (0 or 1 occurrences)
    if not re.fullmatch(r"[A-Za-z]'?", token):
        raise ValueError(f"Invalid literal: {token}")

    variable = token[0]     # variable name

    # boolean value determining whether variable is positive or negated
    positive = not token.endswith("'")

    return variable, positive


# parse SOP expressions
# Ex:
# AB' + A'C
# [
#   [("A", True), ("B", False)],
#   [("A", False), ("C", True)]
# ]
def parse_sop(expression):
    # remove all whitespace from input
    expression = re.sub(r"\s+", "", expression)

    # handle 0 and 1 values
    if expression in ("0", "1"):
        return [[("CONST", expression == "1")]]

    # split the expression into product terms (strings) at each OR operator
    terms = expression.split("+")

    result = []

    for term in terms:
        # malformed input
        if not term:
            raise ValueError("Empty product term")

        # parse '*' and '&' symbols; make sure symbol is between literals
        if (
            term.startswith(("*", "&"))
            or term.endswith(("*", "&"))
        ):
            raise ValueError(f"Invalid AND syntax: {term}")

        # remove symbols
        term = term.replace("*", "").replace("&", "")

        # extract literals from product term
        literals = re.findall(r"[A-Za-z]'?", term)

        # convert each literal into a (variable, polarity) tuple
        # Ex:
        # ["A", "B'"] --> [("A", True), ("B", False)]
        parsed_term = [parse_literal(lit) for lit in literals]

        result.append(parsed_term) 
    return result


# parse POS expressions
# Ex:
# (A+B)(A'+C)
# [
#   [("A", True), ("B", True)],
#   [("A", False), ("C", True)]
# ]
def parse_pos(expression):
    # remove all whitespace from input
    expression = re.sub(r"\s+", "", expression)

    # handle 0 and 1 values
    if expression in ("0", "1"):
        return [[("CONST", expression == "1")]]

    # remove symbols if present
    expression = expression.replace("*", "").replace("&", "")

    # parse each sum:
    # '(' + ... + ')'
    # does not support nested parentheses
    # Ex: "(A+B)(A'+C)" -> ["A+B", "A'+C"]
    groups = re.findall(r"\(([^()]*)\)", expression)

    if not groups:
        raise ValueError("POS must contain parenthesized sum terms")

    result = []

    for group in groups:
        # no empty parenthesis
        if not group:
            raise ValueError("Empty sum term")

        # split by OR operators (+, |)
        literals = re.split(r"[+|]", group)

        # consecutive OR operators create empty literals: delete them
        # Ex: "A++B" -> ["A", "", "B"]
        if any(not lit for lit in literals):
            raise ValueError(f"Invalid POS clause: ({group})")

        # convert each literal into a (variable, polarity) tuple
        parsed_group = [parse_literal(lit) for lit in literals]

        result.append(parsed_group)
    return result


# parse as either SOP or POS
# form:
#   "sop": force SOP parsing
#   "pos": force POS parsing
#   "auto": detect form based on parentheses
def parse_expression(expression, form="auto"):
    expression = expression.strip()

    # assumes SOP has no parenthesis
    if form == "auto":
        form = "pos" if "(" in expression else "sop"

    if form == "sop":
        return form, parse_sop(expression)

    if form == "pos":
        return form, parse_pos(expression)

    raise ValueError("Form must be sop, pos, or auto")


# return list of unique variables in expression
# Ex: AB + A'C -> ["A", "B", "C"]
def get_variables(terms):
    # set automatically eliminates duplicate entries
    variables = set()

    for term in terms:
        for variable, _ in term:

            # do not add constants
            if variable != "CONST":
                variables.add(variable)

    return sorted(variables)


# evaluate parsed expression
def evaluate(terms, form, values):
    if terms == [[("CONST", True)]]:
        return True

    if terms == [[("CONST", False)]]:
        return False

    # evaluate one literal
    # Ex: 
    # Literal: ("A", False)
    # Input: A = 1
    # Result: False because A' = 0
    def literal_value(literal):
        variable, positive = literal

        value = bool(values[variable])

        return value if positive else not value

    if form == "sop":
        # Ex:
        # AB + A'C
        # (A AND B) OR ((NOT A) AND C)
        return any(
            all(literal_value(lit) for lit in term)
            for term in terms
        )

    if form == "pos":
        # Ex:
        # (A+B)(A'+C)
        # (A OR B) AND ((NOT A) OR C)
        return all(
            any(literal_value(lit) for lit in term)
            for term in terms
        )

    raise ValueError(f"Unknown form: {form}")


# generate list of variables, list of tuples, on set, off set
# print these + truth table
def generate_truth_table(terms, form):
    variables = get_variables(terms)

    rows = []
    on_set = []
    off_set = []

    # perform cartesian product of input to get all combinations
    # 2^n combinations (acceptable for simple circuits)
    for index, bits in enumerate(
        product((0, 1), repeat=len(variables))
    ):
        # create a dictionary with variable : value pairs
        # Ex: {"A": 0, "B": 1, "C": 1}
        values = dict(zip(variables, bits))

        # evaluate the Boolean function for this assignment (0 or 1)
        output = int(evaluate(terms, form, values))

        # save the complete truth table row
        rows.append((bits, output))

        if output:
            on_set.append(index)
        else:
            off_set.append(index)

    return variables, rows, on_set, off_set


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
        variables, rows, on_set, off_set = (generate_truth_table(terms, form))

        print(f"Form: {form.upper()}")
        print(f"Parsed terms: {terms}")
        print(f"Variables: {variables}")

        print("\nTruth Table:")
        print(" ".join(variables), "| F")
        print("-" * (2 * len(variables) + 4))

        for bits, output in rows:
            print(" ".join(map(str, bits)), "|", output)

        print("\nON-set:", on_set)
        print("OFF-set:", off_set)

    except ValueError as exc:
        # cli.error() prints the error message and exits with # a nonzero status code
        cli.error(str(exc))

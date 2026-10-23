# EQN style parser
#
# Parses a Boolean expression written in SOP or POS form into a list of terms,
# then evaluates it over every input combination to build a truth table,
# ON-set, and OFF-set.
#
# Supported syntax:
#   variables : single letters A-Z / a-z (case-sensitive: "a" and "A" differ)
#   NOT       : apostrophe after the variable      A'
#   AND       : juxtaposition, '*' or '&'          AB, A*B, A&B
#   OR        : '+' or '|'                          A+B, A|B
#   constants : 0 and 1, alone or inside terms     1, A+0, (A+1)(B)
#   POS       : sum terms in parentheses; a bare single literal is also a
#               valid one-literal sum term          (A+B)(A'+C), (A+B)C
#   whitespace is ignored everywhere

import re
from itertools import product

# regex building blocks shared by both parsers
LITERAL = r"[A-Za-z]'?|[01]"            # A, A', 0, 1
AND_OP = r"[*&]?"                       # optional explicit AND symbol
OR_OPS = r"[+|]"                        # OR symbols


# convert boolean literal into a tuple containing its name and polarity (complemented or not)
# Ex:
# "A" --> ("A", True)
# "B'" --> ("B", False)
# "1" --> ("CONST", True)
# "0" --> ("CONST", False)
def parse_literal(token):
    # check whether string matches the format of:
    # [A-Za-z] : exactly one uppercase or lowercase letter
    # '? : an optional apostrophe (0 or 1 occurrences)
    # or a constant 0 / 1
    if not re.fullmatch(LITERAL, token):
        raise ValueError(f"Invalid literal: '{token}'")

    # constants carry their value in the polarity slot
    if token in ("0", "1"):
        return "CONST", token == "1"

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

    if not expression:
        raise ValueError("Empty expression")

    if "(" in expression or ")" in expression:
        raise ValueError(
            "Parentheses are not allowed in SOP form; "
            "write product terms without them (e.g. AB+C)"
        )

    # split the expression into product terms (strings) at each OR operator
    terms = re.split(OR_OPS, expression)

    result = []

    for term in terms:
        # malformed input, e.g. "A++B", "+A", "A+"
        if not term:
            raise ValueError("Empty product term (check for doubled or dangling '+')")

        # the whole term must be literals, optionally joined by '*' or '&'
        # this rejects stray characters ("A$B", "A''", "C1x") instead of
        # silently dropping them, and rejects misplaced AND symbols ("*A", "A**B")
        if not re.fullmatch(rf"(?:{LITERAL})(?:{AND_OP}(?:{LITERAL}))*", term):
            raise ValueError(f"Invalid product term: '{term}'")

        # extract literals from product term
        literals = re.findall(LITERAL, term)

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

    if not expression:
        raise ValueError("Empty expression")

    # a factor is either a parenthesized sum term or a single bare literal
    # does not support nested parentheses
    factor = rf"\([^()]*\)|{LITERAL}"

    # the whole expression must be factors, optionally joined by '*' or '&'
    # this rejects text the old version silently ignored, e.g. "(A)+(B)"
    # (an OR between sum terms is not POS) or unbalanced parentheses
    if not re.fullmatch(rf"(?:{factor})(?:{AND_OP}(?:{factor}))*", expression):
        raise ValueError(
            "Invalid POS syntax: expected sum terms like (A+B)(A'+C), "
            "joined only by nothing, '*' or '&' "
            "(if you meant SOP, remove the parentheses: e.g. AB+C)"
        )

    # Ex: "(A+B)(A'+C)D" -> ["(A+B)", "(A'+C)", "D"]
    factors = re.findall(factor, expression)

    result = []

    for f in factors:
        # strip parentheses; a bare literal is a one-literal sum term
        group = f[1:-1] if f.startswith("(") else f

        # no empty parenthesis
        if not group:
            raise ValueError("Empty sum term '()'")

        # split by OR operators (+, |)
        literals = re.split(OR_OPS, group)

        # consecutive or dangling OR operators create empty literals: reject them
        # Ex: "A++B" -> ["A", "", "B"]
        if any(not lit for lit in literals):
            raise ValueError(f"Invalid POS clause: ({group})")

        # convert each literal into a (variable, polarity) tuple
        # (parse_literal rejects anything that is not a single literal, e.g. "AB")
        try:
            parsed_group = [parse_literal(lit) for lit in literals]
        except ValueError as exc:
            raise ValueError(
                f"{exc} in clause ({group}); POS clauses may only OR "
                "single literals together"
            ) from None

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
    # evaluate one literal
    # Ex:
    # Literal: ("A", False)
    # Input: A = 1
    # Result: False because A' = 0
    def literal_value(literal):
        variable, positive = literal

        # constants: the polarity slot holds the value itself
        if variable == "CONST":
            return positive

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
    # the first variable is the MSB, so the loop index equals the minterm number
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

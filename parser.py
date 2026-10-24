# EQN style parser
#
# input -> truth table
# 2 input types:
#   1. SOP / POS expression
#      Ex: AB' + A'C      or      (A+B)(A'+C)
#   2. combinational circuit (gate graph) in a .json file
#
# expression syntax:
#   variables : single letters A-Z / a-z (case-sensitive, "a" != "A")
#   NOT       : apostrophe after variable      A'
#   AND       : side by side, '*' or '&'       AB, A*B, A&B
#   OR        : '+' or '|'                     A+B, A|B
#   constants : 0 and 1                        1, A+0, (A+1)(B)
#   whitespace ignored

import re
import json


# regex pieces for SOP + POS parsers
#   [A-Za-z]'?  : 1 letter + optional apostrophe
#   |[01]       : or constant 0 / 1
LITERAL = r"[A-Za-z]'?|[01]"
AND_OP = r"[*&]?"       # optional AND symbol between literals
OR_OPS = r"[+|]"        # either OR symbol

# full product term: 1 literal, then any # of (optional AND + literal)
# (?: ... ) = grouping, like parentheses in math
# Ex: matches "AB'", "A*B'", "A&BC"      rejects "A**B", "*A", "A$B", "A''"
PRODUCT_TERM = "(?:" + LITERAL + ")(?:" + AND_OP + "(?:" + LITERAL + "))*"

# 1 POS factor: "( ... )" sum or bare literal
# Ex: "(A+B')" or "C"
POS_FACTOR = r"\([^()]*\)|" + LITERAL

# full POS expression: factors joined by nothing, '*' or '&'
# Ex: matches "(A+B)(A'+C)", "(A+B)*C"      rejects "(A)+(B)", "(A+B"
POS_EXPRESSION = "(?:" + POS_FACTOR + ")(?:" + AND_OP + "(?:" + POS_FACTOR + "))*"


# index -> bit string, 1st variable = MSB
# Ex:
# to_bits(5, 3) --> "101"
# to_bits(1, 2) --> "01"
def to_bits(index, n):
    bits = ""
    for position in range(n):
        # 1st position = highest bit -> shift n-1, then n-2, ...
        shift = n - 1 - position
        if ((index >> shift) & 1) == 1:
            bits = bits + "1"
        else:
            bits = bits + "0"
    return bits


# literal string -> (name, polarity)
# Ex:
# "A"  --> ("A", True)
# "B'" --> ("B", False)
# "1"  --> ("CONST", True)
# "0"  --> ("CONST", False)
def parse_literal(token):
    # must be exactly 1 literal
    if not re.fullmatch(LITERAL, token):
        raise ValueError(f"Invalid literal: '{token}'")

    # constants: value goes in polarity slot
    if token == "1":
        return "CONST", True
    if token == "0":
        return "CONST", False

    variable = token[0]     # variable name

    # True = plain, False = complemented
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
    # remove whitespace
    expression = re.sub(r"\s+", "", expression)

    if expression == "":
        raise ValueError("Empty expression")

    if "(" in expression or ")" in expression:
        raise ValueError("Parentheses are not allowed in SOP form (Ex: write AB+C)")

    # split at each OR
    # Ex: "AB'+A'C" --> ["AB'", "A'C"]
    terms = re.split(OR_OPS, expression)

    result = []

    for term in terms:
        # empty term = doubled / dangling OR, Ex: "A++B", "A+"
        if term == "":
            raise ValueError("Empty product term (check for doubled or dangling '+')")

        # catch stray chars + misplaced AND symbols
        if not re.fullmatch(PRODUCT_TERM, term):
            raise ValueError(f"Invalid product term: '{term}'")

        # pull out literals
        # Ex: "A*B'" --> ["A", "B'"]
        literals = re.findall(LITERAL, term)

        # literals -> tuples
        # Ex: ["A", "B'"] --> [("A", True), ("B", False)]
        parsed_term = []
        for literal in literals:
            parsed_term.append(parse_literal(literal))

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
    # remove whitespace
    expression = re.sub(r"\s+", "", expression)

    if expression == "":
        raise ValueError("Empty expression")

    # whole string = sum terms joined by nothing, '*' or '&'
    if not re.fullmatch(POS_EXPRESSION, expression):
        raise ValueError(
            "Invalid POS syntax: expected sum terms like (A+B)(A'+C) "
            "(if you meant SOP, remove the parentheses: Ex: AB+C)"
        )

    # split into factors, bare literal = 1-literal sum term
    # no nested parentheses
    # Ex: "(A+B)(A'+C)D" --> ["(A+B)", "(A'+C)", "D"]
    factors = re.findall(POS_FACTOR, expression)

    result = []

    for factor in factors:
        # strip parentheses
        # Ex: "(A+B)" --> "A+B"
        if factor.startswith("("):
            group = factor[1:-1]
        else:
            group = factor

        # no empty parentheses
        if group == "":
            raise ValueError("Empty sum term '()'")

        # split at ORs
        # Ex: "A+B'" --> ["A", "B'"]
        literals = re.split(OR_OPS, group)

        # literals -> tuples
        parsed_group = []
        for literal in literals:
            # double OR -> empty literal, Ex: "A++B" --> ["A", "", "B"]
            if literal == "":
                raise ValueError(f"Invalid POS clause: ({group})")
            parsed_group.append(parse_literal(literal))

        result.append(parsed_group)

    return result


# parse as SOP or POS
# form:
#   "sop": force SOP
#   "pos": force POS
#   "auto": pick based on parentheses
def parse_expression(expression, form="auto"):
    expression = expression.strip()

    # assumes SOP has no parentheses
    if form == "auto":
        if "(" in expression:
            form = "pos"
        else:
            form = "sop"

    if form == "sop":
        return form, parse_sop(expression)

    if form == "pos":
        return form, parse_pos(expression)

    raise ValueError("Form must be sop, pos, or auto")


# unique variables, sorted
# Ex: AB + A'C --> ["A", "B", "C"]
def get_variables(terms):
    variables = []

    for term in terms:
        for variable, positive in term:
            # skip constants + duplicates
            if variable != "CONST" and variable not in variables:
                variables.append(variable)

    variables.sort()
    return variables


# value of 1 literal for given inputs
# Ex:
# Literal: ("A", False)
# Input: A = 1
# Result: False (A' = 0)
def literal_value(literal, values):
    variable, positive = literal

    # constants: polarity slot = value
    if variable == "CONST":
        return positive

    value = values[variable] == 1

    if positive:
        return value
    else:
        return not value


# evaluate parsed expression for 1 input combo
# Ex: AB + A'C w/ {"A": 0, "B": 1, "C": 1} --> True (A'C = 1)
def evaluate(terms, form, values):
    if form == "sop":
        # OR of ANDs: true if any term has all literals true
        for term in terms:
            term_is_true = True
            for literal in term:
                if not literal_value(literal, values):
                    term_is_true = False
                    break
            if term_is_true:
                return True
        return False

    if form == "pos":
        # AND of ORs: false if any term has all literals false
        for term in terms:
            term_is_true = False
            for literal in term:
                if literal_value(literal, values):
                    term_is_true = True
                    break
            if not term_is_true:
                return False
        return True

    raise ValueError(f"Unknown form: {form}")


# evaluate every input combo
# order: optional variable order from file (1st = MSB), default alphabetical
# returns:
#   variables : ["A", "B", "C"]
#   rows      : [("000", 0), ("001", 1), ...]   (input bits, output) per row
#   on_set    : rows where F = 1                 Ex: [1, 3, 4, 5]
#   off_set   : rows where F = 0                 Ex: [0, 2, 6, 7]
def generate_truth_table(terms, form, order=None):
    variables = get_variables(terms)

    # use file's order, but every variable has to be in it
    if order is not None:
        for variable in variables:
            if variable not in order:
                raise ValueError(f"Variable order is missing: {variable}")
        variables = list(order)

    n = len(variables)
    rows = []
    on_set = []
    off_set = []

    # 2^n rows (fine for small circuits)
    # row # = input bits as binary = minterm #
    for index in range(2 ** n):
        bits = to_bits(index, n)

        # variable : value dict
        # Ex: {"A": 0, "B": 1, "C": 1}
        values = {}
        for position in range(n):
            values[variables[position]] = int(bits[position])

        # output for this row (0 or 1)
        if evaluate(terms, form, values):
            output = 1
            on_set.append(index)
        else:
            output = 0
            off_set.append(index)

        # save row
        rows.append((bits, output))

    return variables, rows, on_set, off_set

GATE_TYPES = ["AND", "OR", "NAND", "NOR", "XOR", "XNOR", "NOT", "BUF"]


# read circuit file + check it's valid
# returns dict w/ "inputs", "outputs", "gates"
def load_circuit(path):
    try:
        with open(path, encoding="utf-8") as file:
            circuit = json.load(file)
    except json.JSONDecodeError as error:
        raise ValueError(f"{path}: invalid JSON ({error})")

    for key in ["inputs", "outputs", "gates"]:
        if key not in circuit or not isinstance(circuit[key], list):
            raise ValueError(f"Circuit needs an '{key}' list")

    # inputs become variables -> single letters only
    for name in circuit["inputs"]:
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z]", name):
            raise ValueError(f"Circuit input '{name}' must be a single letter")

    if len(circuit["outputs"]) == 0:
        raise ValueError("Circuit needs at least one output")

    # all signal names so far: inputs, constants, gate outputs
    defined = list(circuit["inputs"]) + ["0", "1"]

    for gate in circuit["gates"]:
        if not isinstance(gate, dict):
            raise ValueError("Each gate must be written as { ... }")

        name = gate.get("name")
        gate_type = gate.get("type")
        gate_inputs = gate.get("inputs")

        # gate names go into Verilog -> letters, digits, _ only
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise ValueError(f"Gate name '{name}' must be letters, digits or _")
        if name in defined:
            raise ValueError(f"Signal '{name}' is defined twice")
        if gate_type not in GATE_TYPES:
            raise ValueError(f"Gate '{name}' has unknown type '{gate_type}'")
        if not isinstance(gate_inputs, list):
            raise ValueError(f"Gate '{name}' needs an 'inputs' list")

        # NOT / BUF: 1 input, everything else: 2+
        if gate_type == "NOT" or gate_type == "BUF":
            if len(gate_inputs) != 1:
                raise ValueError(f"{gate_type} gate '{name}' must have exactly 1 input")
        elif len(gate_inputs) < 2:
            raise ValueError(f"{gate_type} gate '{name}' must have at least 2 inputs")

        defined.append(name)

    # every wire has to come from a real signal
    for gate in circuit["gates"]:
        for signal in gate["inputs"]:
            if signal not in defined:
                raise ValueError(f"Gate '{gate['name']}' uses undefined signal '{signal}'")

    for name in circuit["outputs"]:
        if name not in defined:
            raise ValueError(f"Output '{name}' is not driven by any gate or input")

    # simulate once -> errors out if there's a feedback loop
    all_zero = {}
    for name in circuit["inputs"]:
        all_zero[name] = 0
    simulate_circuit(circuit, all_zero)

    return circuit


# 1 gate's output from its input values (0/1)
# Ex: gate_value("NAND", [1, 1]) --> 0
def gate_value(gate_type, inputs):
    ones = 0
    for value in inputs:
        ones = ones + value

    all_ones = ones == len(inputs)
    any_ones = ones > 0
    odd_ones = ones % 2 == 1      # 3+ input XOR = odd parity

    if gate_type == "AND":
        result = all_ones
    elif gate_type == "OR":
        result = any_ones
    elif gate_type == "NAND":
        result = not all_ones
    elif gate_type == "NOR":
        result = not any_ones
    elif gate_type == "XOR":
        result = odd_ones
    elif gate_type == "XNOR":
        result = not odd_ones
    elif gate_type == "NOT":
        result = inputs[0] == 0
    else:  # BUF
        result = inputs[0] == 1

    if result:
        return 1
    return 0


# every signal value for 1 input combo
# gates in any order: each pass evaluates gates w/ all inputs known, repeat until done
# pass w/ no progress -> gates waiting on each other = loop
# Ex: full adder w/ {"A": 1, "B": 1, "C": 0}
#     --> {"A": 1, "B": 1, "C": 0, "0": 0, "1": 1, "x1": 0, "S": 0, "a1": 1, "a2": 0, "COUT": 1}
def simulate_circuit(circuit, input_values):
    signals = dict(input_values)
    signals["0"] = 0
    signals["1"] = 1

    remaining = list(circuit["gates"])

    while len(remaining) > 0:
        still_waiting = []

        for gate in remaining:
            # all inputs known yet?
            ready = True
            for signal in gate["inputs"]:
                if signal not in signals:
                    ready = False

            if ready:
                values = []
                for signal in gate["inputs"]:
                    values.append(signals[signal])
                signals[gate["name"]] = gate_value(gate["type"], values)
            else:
                still_waiting.append(gate)

        # nothing evaluated -> loop
        if len(still_waiting) == len(remaining):
            names = []
            for gate in still_waiting:
                names.append(gate["name"])
            raise ValueError("Combinational loop (feedback) through gates: " + ", ".join(names))

        remaining = still_waiting

    return signals


# truth table for 1 circuit output
# returns same as generate_truth_table() + output name
def circuit_truth_table(circuit, output=None):
    # default = 1st output
    if output is None:
        output = circuit["outputs"][0]
    if output not in circuit["outputs"]:
        raise ValueError(f"Circuit has no output '{output}' (outputs: {', '.join(circuit['outputs'])})")

    variables = list(circuit["inputs"])
    n = len(variables)
    rows = []
    on_set = []
    off_set = []

    for index in range(2 ** n):
        bits = to_bits(index, n)

        # Ex: {"A": 0, "B": 1, "C": 1}
        values = {}
        for position in range(n):
            values[variables[position]] = int(bits[position])

        output_value = simulate_circuit(circuit, values)[output]

        if output_value == 1:
            on_set.append(index)
        else:
            off_set.append(index)

        rows.append((bits, output_value))

    return variables, rows, on_set, off_set, output

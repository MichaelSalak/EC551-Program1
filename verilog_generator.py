# create structural verilog file from boolean expression
# supports SOP and POS input formats

from parser import get_variables

# 16 bit input bus -> maps straight onto the board's 16 switches
INPUT_WIDTH = 16


# generate structural verilog from parsed SOP/POS terms
#    terms:       term list in parser.py format
#    form:        "sop" or "pos"
#    module_name: name of generated module
#    output_file: .v file to write
#    variables:   full input list (optional)
#                 pass it so a variable dropped by minimization doesn't shift the switches
# Ex: terms for A'C + AB', variables [A, B, C]
#    A -> inputs[0], B -> inputs[1], C -> inputs[2]
#    not g0(not_A, inputs[0]);
#    not g1(not_B, inputs[1]);
#    and g2(term_0, not_A, inputs[2]);
#    and g3(term_1, inputs[0], not_B);
#    or g4(Z, term_0, term_1);
def generate_verilog(terms, form, module_name="boolean_function",
                     output_file="output.v", variables=None):
    if form != "sop" and form != "pos":
        raise ValueError("Form must be 'sop' or 'pos'")

    # input variables, from the terms if no list given
    if variables is None:
        variables = get_variables(terms)

    # 1st 16 variables -> switches, any extra tied to 0
    # Ex: {"A": "inputs[0]", "B": "inputs[1]"}
    variable_map = {}
    for index in range(len(variables)):
        if index < INPUT_WIDTH:
            variable_map[variables[index]] = f"inputs[{index}]"
        else:
            variable_map[variables[index]] = "1'b0"

    # lines of the verilog source
    lines = []

    # unique number for each gate name
    gate_count = 0

    # add 1 gate instance
    #   Ex: add_gate("and", "term_0", ["A", "B"])
    #   --> and g0(term_0, A, B);
    def add_gate(gate_type, output, inputs):
        # gate_count lives outside this function -> nonlocal to change it
        nonlocal gate_count

        signals = ", ".join([output] + inputs)
        lines.append(f"    {gate_type} g{gate_count}({signals});")

        gate_count = gate_count + 1

    # comment showing variable -> switch mapping
    lines.append("// Boolean variable mapping:")
    for variable in variables:
        lines.append(f"// {variable} -> {variable_map[variable]}")
    lines.append("")

    # module header + ports
    lines.append(f"module {module_name} (")
    lines.append(f"    input wire [{INPUT_WIDTH - 1}:0] inputs,")
    lines.append("    output wire Z")
    lines.append(");")
    lines.append("")

    # constant functions, no logic gates needed
    if terms == [[("CONST", True)]]:
        lines.append("    supply1 const_high;")
        add_gate("buf", "Z", ["const_high"])

    elif terms == [[("CONST", False)]]:
        lines.append("    supply0 const_low;")
        add_gate("buf", "Z", ["const_low"])

    else:
        # variables that show up complemented, 1 NOT gate each
        complemented = []
        for term in terms:
            for variable, positive in term:
                if not positive and variable != "CONST" and variable not in complemented:
                    complemented.append(variable)
        complemented.sort()

        # wires for NOT outputs
        for variable in complemented:
            lines.append(f"    wire not_{variable};")

        # 1 wire per product/sum term
        for index in range(len(terms)):
            lines.append(f"    wire term_{index};")

        lines.append("")

        # NOT gates on the bus inputs
        for variable in complemented:
            add_gate("not", f"not_{variable}", [variable_map[variable]])

        if len(complemented) > 0:
            lines.append("")

        # gate types by form
        # SOP: AND inside terms, OR between terms
        # POS: OR inside clauses, AND between clauses
        if form == "sop":
            term_gate = "and"
            final_gate = "or"
        else:
            term_gate = "or"
            final_gate = "and"

        # 1 gate per product/sum term
        for index in range(len(terms)):
            gate_inputs = []

            for variable, positive in terms[index]:
                if variable == "CONST":
                    # constants -> verilog literals
                    if positive:
                        signal = "1'b1"
                    else:
                        signal = "1'b0"

                elif positive:
                    # plain variable -> its bus bit
                    signal = variable_map[variable]

                else:
                    # complemented -> NOT gate output
                    signal = f"not_{variable}"

                gate_inputs.append(signal)

            # 1 literal -> just a buffer
            if len(gate_inputs) == 1:
                add_gate("buf", f"term_{index}", gate_inputs)
            else:
                add_gate(term_gate, f"term_{index}", gate_inputs)

        lines.append("")

        # combine terms into output Z
        term_outputs = []
        for index in range(len(terms)):
            term_outputs.append(f"term_{index}")

        if len(term_outputs) == 1:
            add_gate("buf", "Z", term_outputs)
        else:
            add_gate(final_gate, "Z", term_outputs)

    lines.append("")
    lines.append("endmodule")

    # lines -> 1 string
    verilog_source = "\n".join(lines) + "\n"

    # write to file
    with open(output_file, "w", encoding="utf-8") as file:
        file.write(verilog_source)

    return verilog_source

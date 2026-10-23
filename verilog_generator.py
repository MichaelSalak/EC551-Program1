# create structural verilog file from boolean expression
# suports SOP and POS input formats

from parser import get_variables

# Generate structural Verilog from a parsed SOP/POS expression.
#
#    Parameters:
#        terms: Parsed list of terms from parser.py
#        form: "sop" or "pos"
#        module_name: Name of generated Verilog module
#        output_file: Destination .v file
def generate_verilog(terms, form, module_name="boolean_function",
                     output_file="output.v"):
    if form not in ("sop", "pos"):
        raise ValueError("Form must be 'sop' or 'pos'")

    # extract input variables from the parsed expression
    variables = get_variables(terms)

    # list of strings that will form the Verilog source code
    lines = []

    # unique counter for generated gate instance names
    gate_count = 0

    # Add a structural gate instantiation.
    #
    #   Example:
    #       add_gate("and", "term_0", ["A", "B"])
    #
    #   Produces:
    #       and g0(term_0, A, B);
    def add_gate(gate_type, output, inputs):
        # ensure global gate count updates
        nonlocal gate_count


        signals = ", ".join([output] + inputs)  
        lines.append(f"    {gate_type} g{gate_count}({signals});")

        gate_count += 1

    # generate module declaration
    ports = [f"input wire {v}" for v in variables]
    ports.append("output wire Z")

    # add lines for module header, port declarations, newline
    lines.append(f"module {module_name} (")
    lines.append("    " + ",\n    ".join(ports))
    lines.append(");")
    lines.append("")

    # handle constant functions before generating gates
    if terms == [[("CONST", True)]]:
        lines.append("    supply1 const_high;")
        add_gate("buf", "Z", ["const_high"])

    elif terms == [[("CONST", False)]]:
        lines.append("    supply0 const_low;")
        add_gate("buf", "Z", ["const_low"])

    else:
        # find all variables that appear complemented
        # using a set prevents duplicate NOT gates
        complemented = {
            variable
            for term in terms
            for variable, positive in term
            if not positive
        }

        # generate intermediate wires for complemented inputs
        for variable in sorted(complemented):
            lines.append(f"    wire not_{variable};")

        # generate one wire for each product/sum term
        for index in range(len(terms)):
            lines.append(f"    wire term_{index};")

        lines.append("")

        # generate NOT gates for complemented variables
        for variable in sorted(complemented):
            add_gate("not", f"not_{variable}", [variable])

        if complemented:
            lines.append("")

        # select gate types based on the expression form
        # SOP: AND within terms, OR between terms
        # POS: OR within clauses, AND between clauses
        term_gate = "and" if form == "sop" else "or"
        final_gate = "or" if form == "sop" else "and"

        # generate one gate for each parsed term
        for index, term in enumerate(terms):

            inputs = []

            for variable, positive in term:
                # complemented variables use their NOT wires.
                signal = variable if positive else f"not_{variable}"
                inputs.append(signal)

            # a single literal does not require AND/OR logic
            # use a buffer to connect it to the term wire
            if len(inputs) == 1:
                add_gate("buf", f"term_{index}", inputs)

            else:
                add_gate(term_gate, f"term_{index}", inputs)

        lines.append("")

        # combine the term outputs into the final function
        term_outputs = [
            f"term_{index}" for index in range(len(terms))
        ]

        if len(term_outputs) == 1:
            add_gate("buf", "F", term_outputs)
        else:
            add_gate(final_gate, "F", term_outputs)

    lines.append("")
    lines.append("endmodule")

    # join the source lines into a single string
    verilog_source = "\n".join(lines) + "\n"

    # write to file
    with open(output_file, "w", encoding="utf-8") as file:
        file.write(verilog_source)

    return verilog_source

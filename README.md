# EC551-Program1: Logic Synthesis Engine
### Conor Holland Ruane & Michael Salak

## Simple Project description

This project is a small logic synthesis tool written in Python which recieves an input Boolean function, analyzes the function, minimizes it, and outputs the corresponding minmized function. It then translates that minimized boolean function into verilog cable of running on an FPGA.

# 2 Ways for Input
1. Boolean expression: sum-of-products (SOP) or product-of-sums (POS)
  form inputted via the command line
2. Combinatinoal Logic Circuit: graph of gates (AND, OR, NAND, NOR, XOR, XNOR, NOT, BUF) and the wires between them, stored in a `.json` file.

## Build and run

1. Install Python 3.8 or newer. No other packages are needed.
2. Clone the repo and enter the folder:
   ```bash
   git clone <repo-url>
   cd EC551-Program1
   ```
3. Run the engine on an expression, a `.eqn` file or a `.json` circuit:
   ```bash
   python3 main.py "AB' + A'C"
   python3 main.py examples/example1.eqn
   python3 main.py examples/full_adder.json --output COUT
   ```
4. Optional flags:
   - `--ops 5 7 8`: run only those operations
   - `--verilog-form pos`: build the Verilog from the minimized POS
   - `--verilog-file name.v`: write the Verilog to a different file
5. Put the circuit on the FPGA:
   1. Add `output.v` to a Vivado project along with the provided top module and `.xdc`.
   3. Synthesize, implement, generate bitstream, and program the board.

Expression syntax: single-letter variables, `'` for NOT, `AB` / `A*B` for AND, `+` for OR, and parentheses for POS. Use `python` instead of `python3` on Windows.

## AI usage

We used Claude pretty extensively: it was really important for debugging throughout the entire processs. The most signiciant part of the AI usage was for the parser.py file, as it was extremely difficult to figure out how to parse a graphical CLC, but getting the command-line inputs was a lot more straight-forward and did not require much AI usage apart from debugging. The boolean simplification and output generation was fairly straight forward and required minimal AI use. The point of this project was to apply logic principles so the parser was mostly just needed to get the inputs in the right form (tuples) for further processing. For example: 

    AB' + A'C --> 
    [
      [("A", True), ("B", False)], 
      [("A", False), ("C", True)]
    ].

Additionally, Claude was used at the end of development for polishing the code. We neglected a lot of edge cases during the process and it consistently helped point us in the right direction when we were stuck.
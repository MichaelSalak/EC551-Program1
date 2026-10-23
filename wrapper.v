// wrapper/top module for connecting generated verilog to fpga

module fpga_top(input [15:0] sw, output led);

    boolean_function dut (.inputs(sw), 
                          .Z(led));

endmodule
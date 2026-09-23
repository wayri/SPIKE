// SPDX-License-Identifier: CC0-1.0
module spikes_tristate(
    input wire data_in,
    input wire output_enable,
    output wire data_out
);
    assign data_out = output_enable ? data_in : 1'bz;
endmodule


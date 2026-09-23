-- SPDX-License-Identifier: CC0-1.0
library ieee;
use ieee.std_logic_1164.all;

entity spikes_inverter is
    port (input_value : in std_logic; output_value : out std_logic);
end entity;

architecture rtl of spikes_inverter is
begin
    output_value <= not input_value;
end architecture;


# ---------------------------------------------------------------------------
# Extra constraints for the -plclk bring-up variant only.
#
# H16 is the PYNQ-Z2's SYSCLK.  It is NOT an oscillator.
#
# TUL's own board.xml describes it as "3.3V Single-Ended 125 MHz oscillator
# used as system clock on the board", and that description is misleading:
# TUL_PYNQ_Schematic_R12.pdf shows H16 wired to pin 11 of the RTL8211E-VL --
# the Ethernet PHY's CLK125 output.  There is no separate 125 MHz crystal.
#
# Consequence: with no Ethernet cable in the jack the PHY can drop into
# power-save states and CLK125 stops and restarts, roughly once a second.  So
# this variant wants a cable plugged in -- it does not need a network, a link
# partner is enough to keep the PHY out of power-save.  The design degrades
# safely if the clock does drop: it goes through an MMCM and proc_sys_reset is
# driven from the MMCM's `locked`, so a dropout resets the AXI fabric cleanly
# rather than producing wrong answers.
#
# This is a bring-up aid for a board whose PS has not booted.  Once PYNQ boots,
# use the delivered overlay on FCLK_CLK0 instead.
# ---------------------------------------------------------------------------
set_property -dict {PACKAGE_PIN H16 IOSTANDARD LVCMOS33} [get_ports sys_clk]
create_clock -period 8.000 -name sys_clk [get_ports sys_clk]

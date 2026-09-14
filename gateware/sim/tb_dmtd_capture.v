// ---------------------------------------------------------------------------
// tb_dmtd_capture -- self-checking testbench for the measurement core.
//
//     vivado -mode batch -source gateware/sim.tcl
//
// It drives the real AXI4-Lite handshake rather than a backdoor, runs the
// helper at its true 10.0012344 MHz against a 100 MHz PS clock, and checks the
// things that are expensive to discover on the bench:
//
//   * the register map reads back what the map says it does
//   * the DIFFERENCE between two timestamps equals the number of helper cycles
//     between the two edges -- that difference IS the measurement, so it is
//     the thing worth testing, not the absolute value
//   * beat n lands at slot n, pps n lands at slot 16+n, and nothing bleeds
//   * the CDC delivers: written in the helper domain, read over AXI, untorn
//   * CONTROL bit 0 zeroes the counts and the counter ON THE FIRST WRITE.
//     It did not.  AW and W arrive in the same cycle from SmartConnect and the
//     address register is written with a non-blocking assignment, so the
//     decode compared against the PREVIOUS transaction's address and dropped
//     the first write silently.  That is what this test is here for.
//   * a write to an address that is not CONTROL clears nothing
//   * when the helper stops, ALIVE goes away
//
// The slow dividers are parameters so that liveness and the frequency
// estimator are reachable in microseconds of simulation instead of 105 ms of
// wall clock.  Synthesis uses the defaults; only the test shortens them, and
// the watchdog tracks the divider so the ratio under test is the shipped one.
// ---------------------------------------------------------------------------
`default_nettype none
`timescale 1ps/1ps

module tb_dmtd_capture;

  localparam integer DIV_W  = 8;
  localparam integer LIVE_W = 5;
  localparam integer N_BEAT = 13;
  localparam integer N_PPS  = 12;

  localparam integer HELPER_HALF = 49994;   // 99.988 ns  -> 10.0012 MHz
  localparam integer ACLK_HALF   = 5000;    // 10 ns      -> 100 MHz

  reg helper_run = 1'b1;
  reg helper_clk = 1'b0;
  reg aclk       = 1'b0;
  reg aresetn    = 1'b0;
  always #(HELPER_HALF) if (helper_run) helper_clk = ~helper_clk;
  always #(ACLK_HALF)   aclk = ~aclk;

  reg [N_BEAT-1:0] beat = {N_BEAT{1'b0}};
  reg [N_PPS-1:0]  pps  = {N_PPS{1'b0}};

  reg  [11:0] awaddr = 12'd0;  reg awvalid = 1'b0;  wire awready;
  reg  [31:0] wdata  = 32'd0;  reg wvalid  = 1'b0;  wire wready;
  reg  [3:0]  wstrb  = 4'd0;
  wire [1:0]  bresp;           reg bready  = 1'b0;  wire bvalid;
  reg  [11:0] araddr = 12'd0;  reg arvalid = 1'b0;  wire arready;
  wire [31:0] rdata;           reg rready  = 1'b0;  wire rvalid;
  wire [1:0]  rresp;

  dmtd_capture #(
      .N_BEAT (N_BEAT), .N_PPS (N_PPS), .DIV_W (DIV_W), .LIVE_W (LIVE_W)
  ) dut (
      .helper_clk (helper_clk), .beat (beat), .pps (pps),
      .s_axi_aclk (aclk), .s_axi_aresetn (aresetn),
      .s_axi_awaddr (awaddr), .s_axi_awprot (3'd0),
      .s_axi_awvalid(awvalid), .s_axi_awready(awready),
      .s_axi_wdata  (wdata),   .s_axi_wstrb  (wstrb),
      .s_axi_wvalid (wvalid),  .s_axi_wready (wready),
      .s_axi_bresp  (bresp),   .s_axi_bvalid (bvalid), .s_axi_bready(bready),
      .s_axi_araddr (araddr),  .s_axi_arprot (3'd0),
      .s_axi_arvalid(arvalid), .s_axi_arready(arready),
      .s_axi_rdata  (rdata),   .s_axi_rresp  (rresp),
      .s_axi_rvalid (rvalid),  .s_axi_rready (rready)
  );

  integer errors = 0;
  integer checks = 0;

  task check;
    input [63:0] got;
    input [63:0] want;
    input [56*8:1] what;   // wide enough for the longest label; Verilog
                           // truncates strings from the LEFT, so a short
                           // field silently eats the start of the message
    begin
      checks = checks + 1;
      if (got !== want) begin
        errors = errors + 1;
        $display("FAIL  %0s: got %0d (0x%0h), want %0d", what, got, got, want);
      end else begin
        $display("ok    %0s = %0d (0x%0h)", what, got, got);
      end
    end
  endtask

  task note;
    input ok;
    input [60*8:1] msg;
    begin
      checks = checks + 1;
      if (ok) $display("ok    %0s", msg);
      else begin errors = errors + 1; $display("FAIL  %0s", msg); end
    end
  endtask

  // ---- AXI4-Lite master ---------------------------------------------------
  // AW and W are offered in the same cycle, the way SmartConnect does it,
  // because that ordering is exactly what the write-decode bug depended on.
  task axi_write;
    input [11:0] a;
    input [31:0] d;
    reg aw_done, w_done;
    begin
      @(posedge aclk); #1;
      awaddr = a; awvalid = 1'b1;
      wdata  = d; wstrb = 4'hF; wvalid = 1'b1;
      bready = 1'b1;
      aw_done = 1'b0; w_done = 1'b0;
      while (!(aw_done && w_done)) begin
        @(posedge aclk);
        if (awready) aw_done = 1'b1;
        if (wready)  w_done  = 1'b1;
        #1;
        if (aw_done) awvalid = 1'b0;
        if (w_done)  wvalid  = 1'b0;
      end
      while (bvalid !== 1'b1) @(posedge aclk);
      #1; bready = 1'b0;
    end
  endtask

  task axi_read;
    input  [11:0] a;
    output [31:0] d;
    reg got;
    begin
      @(posedge aclk); #1;
      araddr = a; arvalid = 1'b1; rready = 1'b1;
      while (arready !== 1'b1) @(posedge aclk);
      #1; arvalid = 1'b0;
      got = 1'b0;
      while (!got) begin
        @(posedge aclk);
        if (rvalid === 1'b1) begin d = rdata; got = 1'b1; end
      end
      #1; rready = 1'b0;
    end
  endtask

  // One helper-period-wide pulse, aligned to a helper edge the way the board's
  // retiming flip-flop delivers it.  Consumes exactly two helper edges.
  task pulse_beat; input integer ch; begin
      @(posedge helper_clk); #1; beat[ch] = 1'b1;
      @(posedge helper_clk); #1; beat[ch] = 1'b0;
  end endtask
  task pulse_pps; input integer ch; begin
      @(posedge helper_clk); #1; pps[ch] = 1'b1;
      @(posedge helper_clk); #1; pps[ch] = 1'b0;
  end endtask
  task helper_cycles; input integer n; integer i; begin
      for (i = 0; i < n; i = i + 1) @(posedge helper_clk);
  end endtask
  // long enough for 3 helper stages plus 3 PS stages plus the read pipeline
  task settle; begin helper_cycles(6); repeat (12) @(posedge aclk); end endtask

  function [11:0] ch_ts_lo; input integer n; ch_ts_lo = 12'h200 + n*16 + 0; endfunction
  function [11:0] ch_ts_hi; input integer n; ch_ts_hi = 12'h200 + n*16 + 4; endfunction
  function [11:0] ch_count; input integer n; ch_count = 12'h200 + n*16 + 8; endfunction
  function [11:0] ps_ts_lo; input integer n; ps_ts_lo = 12'h400 + n*16 + 0; endfunction
  function [11:0] ps_ts_hi; input integer n; ps_ts_hi = 12'h400 + n*16 + 4; endfunction
  function [11:0] ps_count; input integer n; ps_count = 12'h400 + n*16 + 8; endfunction

  reg [31:0] v, lo1, lo2, hi1, hi2, before, after;
  reg [31:0] pl1, pl2, hl1, hl2, pp1, pp2, hp;
  integer    gap, i, dps, dh, pred, err;

  initial begin
    $display("=== tb_dmtd_capture : helper 10.0012344 MHz, PS 100 MHz ===");
    repeat (10) @(posedge aclk);
    #1; aresetn = 1'b1;
    repeat (10) @(posedge aclk);

    // ---- identity ---------------------------------------------------------
    axi_read(12'h000, v); check(v, 32'h444D5444, "ID");
    axi_read(12'h004, v); check(v, {8'd1, 8'd1, N_BEAT[7:0], N_PPS[7:0]}, "VERSION 1.1");

    // ---- CONTROL clear must work on the FIRST write -----------------------
    helper_cycles(4 << LIVE_W);           // get the counter well away from 0
    settle;
    axi_read(12'h010, before);
    note(before != 32'd0, "counter is running before the clear");
    axi_write(12'h008, 32'h1);            // the first write of the session
    helper_cycles(4 << LIVE_W);           // let LIVE refresh after the clear
    settle;
    axi_read(12'h010, after);
    note(after < before,
         "FIRST CONTROL write zeroed the free-running counter");
    $display("      LIVE_LO %0d -> %0d", before, after);

    // ---- the measurement: delta-timestamp == delta-helper-cycles ----------
    // Two different channels, with NO bus traffic between the two edges, so
    // the only thing separating them is a counted number of helper cycles.
    axi_write(12'h008, 32'h1);
    settle;
    gap = 977;                            // odd, prime, not a power of two
    pulse_beat(3);                        // eats 2 helper edges
    helper_cycles(gap - 2);
    pulse_beat(4);                        // its capture edge is gap later
    settle;
    axi_read(ch_count(3), v); check(v, 32'd1, "beat 3 count");
    axi_read(ch_count(4), v); check(v, 32'd1, "beat 4 count");
    axi_read(ch_ts_lo(3), lo1); axi_read(ch_ts_hi(3), hi1);
    axi_read(ch_ts_lo(4), lo2); axi_read(ch_ts_hi(4), hi2);
    note((lo1 != 32'd0) || (hi1 != 32'd0), "beat 3 timestamp is not zero");
    check(hi2, hi1, "both timestamps in the same 2^32 epoch");
    check(lo2 - lo1, gap, "timestamp delta equals helper cycles between edges");

    // ---- channel mapping --------------------------------------------------
    axi_write(12'h008, 32'h1);
    settle;
    pulse_pps(5);
    settle;
    axi_read(ch_count(16+5), v); check(v, 32'd1, "pps 5 lands at slot 21");
    axi_read(ch_count(5),    v); check(v, 32'd0, "beat 5 untouched by pps 5");
    axi_read(ch_count(16+6), v); check(v, 32'd0, "slot 22 untouched");
    axi_read(ch_count(13),   v); check(v, 32'd0, "slot 13 has no pin");
    axi_read(12'h0FC,        v); check(v, 32'd0, "unmapped register reads 0");
    axi_read(12'h20C,        v); check(v, 32'd0, "channel word 3 is reserved");
    // v1.1: the same pps edge was also counted and stamped in the PS domain
    axi_read(ps_count(16+5), v); check(v, 32'd1, "pps 5 counted in the PS domain too");
    axi_read(ps_count(16+6), v); check(v, 32'd0, "PS slot 22 untouched");
    axi_read(ps_count(5),    v); check(v, 32'd0, "PS block has nothing for a beat slot");
    axi_read(ps_ts_lo(16+5), v); note(v != 32'd0, "pps 5 PS timestamp is not zero");
    axi_read(12'h40C,        v); check(v, 32'd0, "PS channel word 3 is reserved");

    // ---- v1.1: PS timestamps resolve 10 ns, and map onto the helper scale --
    // Two pps 7 edges exactly 200 helper cycles apart are 1999.75 PS clocks
    // apart; the PS side must see 2000 +/- 1 (each edge is quantised once).
    axi_write(12'h008, 32'h1);
    settle;
    pulse_pps(7);                         // eats 2 helper edges
    axi_read(ps_ts_lo(16+7), pp1);
    axi_read(ch_ts_lo(16+7), hp);
    helper_cycles(198);
    pulse_pps(7);
    settle;
    axi_read(ps_count(16+7), v); check(v, 32'd2, "two pps 7 edges in the PS domain");
    axi_read(ps_ts_lo(16+7), pp2);
    dps = pp2 - pp1;
    note(dps >= 1998 && dps <= 2002, "200 helper cycles of pps spacing is 2000 +/- 2 PS clocks");
    $display("      PS delta = %0d clocks for 200 helper cycles (expect 1999.75)", dps);
    // The pair: (LIVE, LIVE_PS) taken at the same instant, twice, gives the
    // scale between the two counters...
    helper_cycles(4 << LIVE_W); settle;
    axi_read(12'h010, hl1); axi_read(12'h01C, pl1);
    helper_cycles(8 << LIVE_W); settle;
    axi_read(12'h010, hl2); axi_read(12'h01C, pl2);
    dh  = hl2 - hl1;
    dps = pl2 - pl1;
    note(dh > 0 && dps > 0, "the pair advances in both domains");
    note((dps * 100 > dh * 990) && (dps * 100 < dh * 1010),
         "pair ratio is 9.9988 PS clocks per helper cycle within 1%");
    $display("      pair: %0d helper cycles <-> %0d PS clocks", dh, dps);
    // ...and with it a pps PS-timestamp predicts the helper-domain timestamp
    // of the same edge to within the two synchronisers' latency.
    axi_read(ch_ts_lo(16+7), hp);          // helper-domain stamp of the 2nd edge
    pred = hl2 - ((pl2 - pp2) * 10000) / 99988;   // helper cycles at pp2
    err  = pred - hp;
    note(err >= -6 && err <= 6, "PS timestamp maps onto the helper timestamp within 6 cycles");
    $display("      pps 7: helper stamp %0d, predicted from PS stamp %0d (err %0d)", hp, pred, err);

    // ---- a write that is not to CONTROL must clear nothing ---------------
    axi_write(12'h000, 32'hFFFF_FFFF);
    settle;
    axi_read(ch_count(16+5), v); check(v, 32'd1, "counts survive a write to 0x000");
    axi_write(12'h008, 32'h0);            // CONTROL, but bit 0 clear
    settle;
    axi_read(ch_count(16+5), v); check(v, 32'd1, "counts survive CONTROL with bit0=0");

    // ---- every beat and every pps, independently -------------------------
    axi_write(12'h008, 32'h1);
    settle;
    for (i = 0; i < N_BEAT; i = i + 1)
      repeat (i + 1) begin pulse_beat(i); helper_cycles(3); end
    for (i = 0; i < N_PPS; i = i + 1)
      repeat (i + 1) begin pulse_pps(i); helper_cycles(3); end
    settle;
    for (i = 0; i < N_BEAT; i = i + 1) begin
      axi_read(ch_count(i), v);
      note(v === i + 1, "beat channel counted exactly its own edges");
      if (v !== i + 1) $display("      beat %0d: got %0d want %0d", i, v, i + 1);
    end
    for (i = 0; i < N_PPS; i = i + 1) begin
      axi_read(ch_count(16 + i), v);
      note(v === i + 1, "pps channel counted exactly its own edges");
      if (v !== i + 1) $display("      pps %0d: got %0d want %0d", i, v, i + 1);
    end

    // ---- liveness and the helper frequency estimate ----------------------
    // HELPER is PS clocks per 2^DIV_W helper cycles; 100 / 10.0012344 = 9.9988.
    helper_cycles(3 << DIV_W);
    settle;
    axi_read(12'h018, v); check(v, 32'd1, "ALIVE while the helper runs");
    axi_read(12'h00C, v);
    note((v > (10 * (1 << DIV_W) * 99) / 100) &&
         (v < (10 * (1 << DIV_W) * 101) / 100),
         "HELPER is within 1% of the expected PS-clocks-per-tick");
    $display("      HELPER = %0d PS clocks per %0d helper cycles (expect ~%0d)",
             v, 1 << DIV_W, 10 * (1 << DIV_W));

    // ---- the helper stops -------------------------------------------------
    // The watchdog is 2^(DIV_W+4) PS clocks, i.e. 1.6 tick periods, whatever
    // DIV_W is -- so this is the shipped ratio, just scaled down.
    helper_run = 1'b0;
    repeat (40 << DIV_W) @(posedge aclk);
    axi_read(12'h018, v); check(v, 32'd0, "ALIVE drops when the helper stops");
    axi_read(12'h00C, v); check(v, 32'd0, "HELPER reads 0 when the helper stops");
    axi_read(12'h000, v); check(v, 32'h444D5444, "AXI still answers with no helper clock");

    $display("=== %0d checks, %0d failures ===", checks, errors);
    if (errors == 0) $display("TB PASS"); else $display("TB FAIL");
    $finish;
  end

  // A test that hangs tells you nothing about why.
  initial begin
    #1500000000;                      // 1.5 ms
    $display("FAIL  testbench timeout");
    $display("TB FAIL");
    $finish;
  end

endmodule
`default_nettype wire

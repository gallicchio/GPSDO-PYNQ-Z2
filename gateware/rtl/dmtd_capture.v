// ---------------------------------------------------------------------------
// dmtd_capture -- timestamp every beat and pps edge against the helper clock.
//
// WHAT THIS MEASURES
//
// The front-end board samples each GPSDO's 10 MHz with a common helper at
// 10.0012344 MHz, so each channel emits a ~1234.4 Hz beat whose EDGE TIME
// carries that oscillator's phase multiplied by N = f_helper/(f_helper -
// f_signal) = 8101.  All this module does -- and all it should do -- is record
// WHEN each beat edge happened, counted in helper cycles.
//
// One helper cycle is 99.988 ns; divided by N that is 12.3 ps referred to the
// 10 MHz input.  So a plain integer counter clocked by the helper, latched on
// each beat edge, IS the picosecond measurement.  Nothing here needs to be
// fast or clever; it needs to not lose count.
//
// WHY THE BEAT EDGE IS ALREADY ALIGNED TO A HELPER EDGE
//
// On the board each channel ends in two flip-flops clocked by the helper, the
// second of which retimes.  A beat edge arriving here is therefore a delayed
// copy of a helper edge -- delayed by the board, by the 200 ohm series
// resistor the PYNQ puts in every header GPIO, and by the trace.  That skew is
// fixed but unknown, so the beat transition may land anywhere relative to our
// sampling edge, INCLUDING on it.  Two consequences, both deliberate:
//
//   * The input goes through a synchroniser.  With 810 us between events the
//     metastability MTBF is beyond any timescale that matters.
//   * If the skew does put the transition on our sampling edge, the captured
//     timestamp can be off by one helper cycle -- which is 12.3 ps referred to
//     the input, i.e. exactly the quantisation already accepted.  The worst
//     case is the design resolution, so no phase shifting is used.  If a
//     channel dithers by one count at bring-up, an MMCM phase shift on the
//     capture clock is the fix -- but note a 7-series MMCM's minimum input is
//     10 MHz and the helper is 10.0012 MHz, so that is marginal by design.
//
// CLOCK DOMAIN CROSSING
//
// Timestamps are written in the helper domain and read in the PS domain, using
// "stable data, synchronised control": the helper side writes the timestamp
// and then toggles one bit; the PS side synchronises the toggle and, on seeing
// it change, copies the data.  That is safe HERE for a specific reason -- the
// data cannot change again for at least 810 us (beats) or 1 s (pps), while the
// copy happens within ~30 ns of the toggle.  Do not reuse this pattern where
// the source can update quickly.
//
// THE PPS, TWICE  (v1.1, round 28)
//
// A beat timestamp is modulo one 10 MHz cycle: the beat wraps every 810 us,
// which is exactly 100 ns of input phase, so two oscillators 100 ns apart
// read the same.  The 1 pps is meant to say WHICH 100 ns cycle -- but a pps
// timestamped in helper cycles is itself quantised to 100 ns, which is the
// very ambiguity it is supposed to resolve.  (Rounds 10-27 promised a 200 MHz
// / 5 ns domain for this; none was ever built.  Two of round 28's reviewers
// noticed.)
//
// So every pps is now timestamped a second time, in the PS clock domain, by a
// free-running 100 MHz counter: 10 ns resolution, which picks a 100 ns cycle
// with margin.  The two domains are tied together by a PAIR register: at each
// LIVE refresh the PS side latches its own counter alongside the helper
// counter it just received, so software has (helper_cycles, ps_ticks) samples
// of the same instants and can map either scale onto the other.  The pps
// PS-timestamps are plain PS-domain registers -- no CDC, since the AXI bus
// is in that domain -- and can also be read against each other directly as a
// 10 ns time-interval counter between any two GPSDOs' pps outputs.
//
// REGISTER MAP (AXI4-Lite, 32-bit, 4 kB)
//
//   0x000 R   ID        0x444D5444 = "DMTD"
//   0x004 R   VERSION   {8'maj, 8'min, 8'N_BEAT, 8'N_PPS}   = 1.1
//   0x008 RW  CONTROL   write bit0 = 1: zero the counters and all edge counts
//   0x00C R   HELPER    PS-clock ticks per 2^20 helper cycles; 0 = no helper
//   0x010 R   LIVE_LO   free-running helper counter, refreshed every ~102 us
//   0x014 R   LIVE_HI
//   0x018 R   ALIVE     bit0 = helper clock is running
//   0x01C R   LIVE_PS_LO  the PS counter, latched when LIVE_LO/HI last
//   0x020 R   LIVE_PS_HI  arrived (v1.1): the (helper, PS) pair
//
//   0x200 + 16*n + 0  R  channel n timestamp low        (helper cycles)
//   0x200 + 16*n + 4  R  channel n timestamp high
//   0x200 + 16*n + 8  R  channel n edge count (free-running, wraps at 2^32)
//   0x200 + 16*n + 12 R  reserved, reads 0
//
//   0x400 + 16*n + 0  R  channel n PS timestamp low     (PS clocks, v1.1;
//   0x400 + 16*n + 4  R  channel n PS timestamp high     pps slots only)
//   0x400 + 16*n + 8  R  channel n PS-domain edge count
//   0x400 + 16*n + 12 R  reserved, reads 0
//
//   n = 0  .. N_BEAT-1      the beats,       BEAT_00 .. BEAT_12
//   n = 16 .. 16+N_PPS-1    the pps returns, PPS_00  .. PPS_11
//
// Read {timestamp, edge count} together: the count says how many edges have
// happened since you last looked, so polling from Python at 10 Hz loses no
// information even though beats arrive at 1234 Hz.  You do not need every
// edge; you need a timestamp and to know which beat it belongs to.
// ---------------------------------------------------------------------------
`default_nettype none

module dmtd_capture #(
    parameter integer N_BEAT = 13,
    parameter integer N_PPS  = 12,
    // The two slow dividers are parameters only so that a testbench can reach
    // liveness and the frequency estimator in microseconds instead of 105 ms.
    // Nothing but the testbench should ever change them.
    parameter integer DIV_W  = 20,   // helper cycles per frequency/liveness tick
    parameter integer LIVE_W = 10,   // helper cycles per refresh of LIVE_LO/HI
    parameter integer C_S_AXI_ADDR_WIDTH = 12,
    parameter integer C_S_AXI_DATA_WIDTH = 32
) (
    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 helper_clk CLK" *)
    (* X_INTERFACE_PARAMETER = "ASSOCIATED_RESET none, FREQ_HZ 10001234" *)
    input  wire                               helper_clk,
    input  wire [N_BEAT-1:0]                  beat,
    input  wire [N_PPS-1:0]                   pps,

    (* X_INTERFACE_INFO = "xilinx.com:signal:clock:1.0 s_axi_aclk CLK" *)
    (* X_INTERFACE_PARAMETER = "ASSOCIATED_BUSIF S_AXI, ASSOCIATED_RESET s_axi_aresetn" *)
    input  wire                               s_axi_aclk,
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 s_axi_aresetn RST" *)
    (* X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *)
    input  wire                               s_axi_aresetn,
    input  wire [C_S_AXI_ADDR_WIDTH-1:0]      s_axi_awaddr,
    input  wire [2:0]                         s_axi_awprot,
    input  wire                               s_axi_awvalid,
    output wire                               s_axi_awready,
    input  wire [C_S_AXI_DATA_WIDTH-1:0]      s_axi_wdata,
    input  wire [(C_S_AXI_DATA_WIDTH/8)-1:0]  s_axi_wstrb,
    input  wire                               s_axi_wvalid,
    output wire                               s_axi_wready,
    output wire [1:0]                         s_axi_bresp,
    output wire                               s_axi_bvalid,
    input  wire                               s_axi_bready,
    input  wire [C_S_AXI_ADDR_WIDTH-1:0]      s_axi_araddr,
    input  wire [2:0]                         s_axi_arprot,
    input  wire                               s_axi_arvalid,
    output wire                               s_axi_arready,
    output wire [C_S_AXI_DATA_WIDTH-1:0]      s_axi_rdata,
    output wire [1:0]                         s_axi_rresp,
    output wire                               s_axi_rvalid,
    input  wire                               s_axi_rready
);

  localparam integer NCH  = 32;                // slots; beats at 0, pps at 16
  localparam integer PPS0 = 16;
  localparam [31:0]  ID   = 32'h444D_5444;     // "DMTD"

  // Declared here, before the helper domain uses it, because the clear
  // request originates on the PS side and crosses into the helper domain.
  reg clr_tog_ps = 1'b0;

  // =========================================================================
  // helper clock domain
  // =========================================================================
  wire [NCH-1:0] raw;
  genvar g;
  generate
    for (g = 0; g < NCH; g = g + 1) begin : g_map
      if (g < N_BEAT)                         assign raw[g] = beat[g];
      else if (g >= PPS0 && g < PPS0 + N_PPS) assign raw[g] = pps[g-PPS0];
      else                                    assign raw[g] = 1'b0;
    end
  endgenerate

  (* ASYNC_REG = "TRUE" *) reg clr_m = 1'b0;
  reg clr_s = 1'b0, clr_p = 1'b0;
  wire do_clear = clr_s ^ clr_p;

  reg [63:0] counter = 64'd0;
  always @(posedge helper_clk) begin
    clr_m   <= clr_tog_ps;
    clr_s   <= clr_m;
    clr_p   <= clr_s;
    counter <= do_clear ? 64'd0 : counter + 64'd1;
  end

  reg [63:0]    ts_h  [0:NCH-1];
  reg [31:0]    cnt_h [0:NCH-1];
  reg [NCH-1:0] tog_h = {NCH{1'b0}};

  generate
    for (g = 0; g < NCH; g = g + 1) begin : g_cap
      (* ASYNC_REG = "TRUE" *) reg s0 = 1'b0;
      reg s1 = 1'b0, s2 = 1'b0;
      initial begin ts_h[g] = 64'd0; cnt_h[g] = 32'd0; end
      always @(posedge helper_clk) begin
        s0 <= raw[g];       // absorbs metastability
        s1 <= s0;           // clean value
        s2 <= s1;           // its history, so (s1 & ~s2) is a rising edge
        if (do_clear) begin
          cnt_h[g] <= 32'd0;
        end else if (s1 && !s2) begin
          ts_h [g] <= counter;
          cnt_h[g] <= cnt_h[g] + 32'd1;
          tog_h[g] <= ~tog_h[g];
        end
      end
    end
  endgenerate

  // A slow tick for liveness, and a periodic refresh of "what time is it now".
  reg [DIV_W-1:0] divider  = {DIV_W{1'b0}};
  reg             slow_tog = 1'b0;
  reg [63:0]      live_h   = 64'd0;
  reg             live_tog = 1'b0;
  always @(posedge helper_clk) begin
    divider <= divider + 1'b1;
    if (divider == {DIV_W{1'b0}}) slow_tog <= ~slow_tog;      // every 2^DIV_W
    if (divider[LIVE_W-1:0] == {LIVE_W{1'b0}}) begin          // every 2^LIVE_W
      live_h   <= counter;
      live_tog <= ~live_tog;
    end
  end

  // =========================================================================
  // PS clock domain
  // =========================================================================
  reg [63:0] ts_ps  [0:NCH-1];
  reg [31:0] cnt_ps [0:NCH-1];
  generate
    for (g = 0; g < NCH; g = g + 1) begin : g_ps
      (* ASYNC_REG = "TRUE" *) reg t0 = 1'b0;
      reg t1 = 1'b0, t2 = 1'b0;
      initial begin ts_ps[g] = 64'd0; cnt_ps[g] = 32'd0; end
      always @(posedge s_axi_aclk) begin
        t0 <= tog_h[g];
        t1 <= t0;
        t2 <= t1;
        if (t1 ^ t2) begin          // data settled >= 2 PS clocks ago and
          ts_ps [g] <= ts_h [g];    // cannot change again for >= 810 us
          cnt_ps[g] <= cnt_h[g];
        end
      end
    end
  endgenerate

  // ---- v1.1: the PS-domain counter, the pps PS-timestamps, the pair ------
  // Cleared by the same CONTROL write that clears the helper counter (two or
  // three clocks apart in each domain, which the pair register absorbs).
  reg        clr_ps_d = 1'b0;
  wire       do_clear_ps = clr_tog_ps ^ clr_ps_d;
  reg [63:0] psc = 64'd0;
  always @(posedge s_axi_aclk) begin
    clr_ps_d <= clr_tog_ps;
    psc      <= do_clear_ps ? 64'd0 : psc + 64'd1;
  end

  reg [63:0] pts_ps  [0:NCH-1];
  reg [31:0] pcnt_ps [0:NCH-1];
  generate
    for (g = 0; g < NCH; g = g + 1) begin : g_pps_ps
      initial begin pts_ps[g] = 64'd0; pcnt_ps[g] = 32'd0; end
      if (g >= PPS0 && g < PPS0 + N_PPS) begin : g_has_pps
        (* ASYNC_REG = "TRUE" *) reg q0 = 1'b0;
        reg q1 = 1'b0, q2 = 1'b0;
        always @(posedge s_axi_aclk) begin
          q0 <= pps[g - PPS0];
          q1 <= q0;
          q2 <= q1;
          if (do_clear_ps) begin
            pcnt_ps[g] <= 32'd0;
          end else if (q1 && !q2) begin
            pts_ps [g] <= psc;
            pcnt_ps[g] <= pcnt_ps[g] + 32'd1;
          end
        end
      end
    end
  endgenerate

  (* ASYNC_REG = "TRUE" *) reg lv0 = 1'b0;
  reg lv1 = 1'b0, lv2 = 1'b0;
  reg [63:0] live_ps  = 64'd0;
  reg [63:0] live_psc = 64'd0;          // psc at the moment live_ps was taken
  always @(posedge s_axi_aclk) begin
    lv0 <= live_tog; lv1 <= lv0; lv2 <= lv1;
    if (lv1 ^ lv2) begin
      live_ps  <= live_h;
      live_psc <= psc;
    end
  end

  // Helper frequency: PS clocks between successive 2^20-helper-cycle ticks.
  (* ASYNC_REG = "TRUE" *) reg sw0 = 1'b0;
  reg sw1 = 1'b0, sw2 = 1'b0;
  reg [31:0] hz_run = 32'd0, hz_lat = 32'd0;
  // 2^(DIV_W+4) PS clocks is 1.6 tick periods at 100 MHz against 10.0012 MHz:
  // long enough never to trip while the helper runs, short enough that a dead
  // helper is reported in well under a second.  Tying it to DIV_W keeps that
  // ratio when a testbench shortens the divider.
  localparam integer WD_W = DIV_W + 4;
  reg [WD_W-1:0] watchdog = {WD_W{1'b0}};
  reg        alive = 1'b0;
  always @(posedge s_axi_aclk) begin
    sw0 <= slow_tog; sw1 <= sw0; sw2 <= sw1;
    if (sw1 ^ sw2) begin
      hz_lat   <= hz_run;
      hz_run   <= 32'd1;
      watchdog <= {WD_W{1'b0}};
      alive    <= 1'b1;
    end else begin
      hz_run <= hz_run + 32'd1;
      if (&watchdog) begin
        alive  <= 1'b0;
        hz_lat <= 32'd0;
      end else begin
        watchdog <= watchdog + 1'b1;
      end
    end
  end

  // =========================================================================
  // AXI4-Lite
  // =========================================================================
  reg        awready = 0, wready = 0, bvalid = 0, arready = 0, rvalid = 0;
  reg [1:0]  bresp = 2'b00, rresp = 2'b00;
  reg [C_S_AXI_ADDR_WIDTH-1:0] araddr_q = 0, awaddr_q = 0;
  reg        aw_hs = 0, w_hs = 0;
  reg [C_S_AXI_DATA_WIDTH-1:0] wdata_q = 0;

  assign s_axi_awready = awready;
  assign s_axi_wready  = wready;
  assign s_axi_bvalid  = bvalid;
  assign s_axi_bresp   = bresp;
  assign s_axi_arready = arready;
  assign s_axi_rvalid  = rvalid;
  assign s_axi_rresp   = rresp;

  // Channel block is 0x200..0x3FF: one bit selects it and five address the
  // slot, which is why the map starts at 0x200 and not 0x100.  The PS-domain
  // block is the same shape at 0x400..0x5FF, selected by the next bit.
  wire       sel_ps = araddr_q[10];
  wire       sel_ch = araddr_q[9] & ~araddr_q[10];
  wire [4:0] rd_ch  = araddr_q[8:4];
  wire [1:0] rd_off = araddr_q[3:2];

  // The read data is REGISTERED, not driven combinationally onto RDATA.
  // Selecting one of 32 channels x three 32-bit words is a wide mux, and
  // driven straight to the interconnect it cost 10.96 ns of a 10 ns period --
  // six logic levels and 86% routing.  Giving the mux its own pipeline stage
  // costs one clock of read latency, which AXI4-Lite allows for free, and
  // turns the critical path into a short register-to-register hop.
  reg [31:0] rdata_mux;
  reg [31:0] rdata_q = 32'd0;
  reg        rd_pending = 1'b0;
  always @(*) begin
    if (sel_ps) begin
      case (rd_off)
        2'd0:    rdata_mux = pts_ps [rd_ch][31:0];
        2'd1:    rdata_mux = pts_ps [rd_ch][63:32];
        2'd2:    rdata_mux = pcnt_ps[rd_ch];
        default: rdata_mux = 32'd0;
      endcase
    end else if (sel_ch) begin
      case (rd_off)
        2'd0:    rdata_mux = ts_ps [rd_ch][31:0];
        2'd1:    rdata_mux = ts_ps [rd_ch][63:32];
        2'd2:    rdata_mux = cnt_ps[rd_ch];
        default: rdata_mux = 32'd0;
      endcase
    end else begin
      case (araddr_q[7:2])
        6'h00:   rdata_mux = ID;
        6'h01:   rdata_mux = {8'd1, 8'd1, N_BEAT[7:0], N_PPS[7:0]};
        6'h02:   rdata_mux = {31'd0, clr_tog_ps};
        6'h03:   rdata_mux = hz_lat;
        6'h04:   rdata_mux = live_ps[31:0];
        6'h05:   rdata_mux = live_ps[63:32];
        6'h06:   rdata_mux = {31'd0, alive};
        6'h07:   rdata_mux = live_psc[31:0];
        6'h08:   rdata_mux = live_psc[63:32];
        default: rdata_mux = 32'd0;
      endcase
    end
  end
  assign s_axi_rdata = rdata_q;

  always @(posedge s_axi_aclk) begin
    if (!s_axi_aresetn) begin
      awready <= 1'b0; wready <= 1'b0; bvalid <= 1'b0; bresp <= 2'b00;
      arready <= 1'b0; rvalid <= 1'b0; rresp <= 2'b00;
      rd_pending <= 1'b0;
      aw_hs <= 1'b0; w_hs <= 1'b0;
    end else begin
      // ---- write ---------------------------------------------------------
      // AXI lets the address and the data arrive in either order, and
      // SmartConnect offers both in the SAME cycle.  So each channel is
      // accepted independently into its own holding register and the decode
      // waits until both have arrived.
      //
      // Decoding at the moment W is accepted -- which is what this did --
      // is wrong: awaddr_q is written with a non-blocking assignment, so in
      // the cycle AW is accepted it still holds the PREVIOUS transaction's
      // address.  With AW and W together, every write decoded against the
      // address of the write before it, and the first write of the session
      // compared against the reset value 0x000 and was silently dropped.
      // Nothing reported an error: BRESP was still OKAY.
      if (!aw_hs && s_axi_awvalid && !bvalid) begin
        awready  <= 1'b1;
        aw_hs    <= 1'b1;
        awaddr_q <= s_axi_awaddr;
      end else begin
        awready <= 1'b0;
      end

      if (!w_hs && s_axi_wvalid && !bvalid) begin
        wready  <= 1'b1;
        w_hs    <= 1'b1;
        wdata_q <= s_axi_wdata;
      end else begin
        wready <= 1'b0;
      end

      // WSTRB is ignored: the only writable bit is CONTROL[0], and AXI4-Lite
      // from the PS and from jtag_axi always writes full 32-bit words.
      if (aw_hs && w_hs && !bvalid) begin
        if (awaddr_q[11:0] == 12'h008 && wdata_q[0])
          clr_tog_ps <= ~clr_tog_ps;      // one edge into the helper domain
        aw_hs  <= 1'b0;
        w_hs   <= 1'b0;
        bvalid <= 1'b1;
        bresp  <= 2'b00;
      end else if (bvalid && s_axi_bready) begin
        bvalid <= 1'b0;
      end

      // ---- read ----------------------------------------------------------
      if (!arready && s_axi_arvalid && !rvalid && !rd_pending) begin
        arready    <= 1'b1;
        araddr_q   <= s_axi_araddr;
        rd_pending <= 1'b1;      // the mux gets this whole cycle
      end else begin
        arready <= 1'b0;
      end

      if (rd_pending) begin
        rdata_q    <= rdata_mux;
        rd_pending <= 1'b0;
        rvalid     <= 1'b1;
        rresp      <= 2'b00;
      end else if (rvalid && s_axi_rready) begin
        rvalid <= 1'b0;
      end
    end
  end

endmodule

`default_nettype wire

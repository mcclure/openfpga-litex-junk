#!/usr/bin/env python3

#
# This file is part of LiteX-Boards.
#
# Copyright (c) 2023 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

# ./analog_pocket.py --uart-name=jtag_uart --build --load
# litex_term jtag --jtag-config=openocd_usb_blaster.cfg

# Set up the import paths for the LiteX packages
import vendor
from litex.soc.integration.soc import SoCRegion
from litex.soc.interconnect.csr import CSR, CSRStatus, CSRStorage

from litex.soc.cores.video import VideoVGAPHY
from litex.soc.interconnect import wishbone

from migen import *

from litex.gen import *

import verilog_platform as analogue_pocket

from litex.soc.integration.soc_core import *
from litex.soc.integration.builder import *

from litex.build.io import DDROutput

from litex.soc.cores.clock import CycloneVPLL

from litedram.modules import AS4C32M16
from litedram.phy.gensdrphy import HalfRateGENSDRPHY

# CRG ----------------------------------------------------------------------------------------------

CLOCK_SPEED = 52.94e6

class _CRG(LiteXModule):
    def __init__(self, platform: analogue_pocket.Platform, sys_clk_freq):
        # `rst` is a magic CRG signal that is automatically wired to the output of the SoC reset
        self.rst          = Signal()
        # LiteX expects a `sys` clock domain, so we can't rename it
        self.cd_sys         = ClockDomain()
        # LiteX also expects a `sys2x` clock domain when using double rate SDRAM, and it can't be renamed
        self.cd_sys2x       = ClockDomain()
        self.cd_sys2x_90deg = ClockDomain()
        self.cd_vid         = ClockDomain()

        reset_pin = platform.request("reset")

        clk_sys = platform.request("clk_sys")
        self.comb += self.cd_sys.clk.eq(clk_sys)
        self.comb += self.cd_sys.rst.eq(self.rst | reset_pin)

        clk_sys2x = platform.request("clk_sys2x")
        self.comb += self.cd_sys2x.clk.eq(clk_sys2x)
        self.comb += self.cd_sys2x.rst.eq(self.rst | reset_pin)

        clk_sys2x_90deg = platform.request("clk_sys2x_90deg")
        self.comb += self.cd_sys2x_90deg.clk.eq(clk_sys2x_90deg)

        clk_vid = platform.request("clk_vid")
        self.comb += self.cd_vid.clk.eq(clk_vid)

        # # #

        # SDRAM clock
        sdram_clk = clk_sys2x_90deg
        self.specials += DDROutput(1, 0, platform.request("sdram_clock"), sdram_clk)

        # UART
        # cart = platform.request("cart")
        # self.comb += cart.tran_bank0_dir.eq(1)

        # self.comb += cart.tran_pin31_dir.eq(0)

        # platform.add_extension([
        #     ("cart_serial", 0, 
        #         Subsignal("tx", cart.tran_bank0[2]), 
        #         Subsignal("rx", cart.tran_pin31)
        #     )])

# BaseSoC ------------------------------------------------------------------------------------------

class BaseSoC(SoCCore):
    def __init__(self, sys_clk_freq, **kwargs):
        platform = analogue_pocket.Platform()

        # CRG --------------------------------------------------------------------------------------
        self.crg = _CRG(platform, sys_clk_freq)

        # SoCCore ----------------------------------------------------------------------------------
        SoCCore.__init__(self, platform, sys_clk_freq, ident="LiteX SoC on Analog Pocket", **kwargs)

        # reset = platform.request("reset")
        # # self.comb += self.cpu.reset.eq(self.crg.rst)
        # self.comb += self.cpu.reset.eq(reset)

        # UARTBone

        # self.add_uart(name="uart2", uart_name="cart_serial", baudrate=115200)
        # self.add_uart(name="jtag_uart", uart_name="jtag_uart", baudrate=115200, fifo_depth=16)

        # SDR SDRAM --------------------------------------------------------------------------------
        if not self.integrated_main_ram_size:
            self.sdrphy = HalfRateGENSDRPHY(platform.request("sdram"), sys_clk_freq)
            self.add_sdram("sdram",
                phy           = self.sdrphy,
                module        = AS4C32M16(sys_clk_freq, "1:2"),
                l2_cache_size = kwargs.get("l2_size", 8192)
            )

        # This only works with modifications to vendor/litex/litex/soc/cores/video.py to remove the SDR and DDR outputs
        self.submodules.videophy = VideoVGAPHY(platform.request("vga"))
        self.add_video_framebuffer(phy=self.videophy, timings=[
            "266x240@60Hz",
            {
                "pix_clk"       : CLOCK_SPEED / 10,
                "h_active"      : 266,
                "h_blanking"    : 80,
                "h_sync_offset" : 8,
                "h_sync_width"  : 32,
                "v_active"      : 240,
                "v_blanking"    : 15,
                "v_sync_offset" : 1,
                "v_sync_width"  : 8,
            }], format="rgb565", clock_domain="vid")
        # self.add_video_terminal(phy=self.videophy, timings="320x200@60Hz", clock_domain="vid")

        self.add_controller_csr(platform)
        self.add_apf_bridge_csr(platform)
        self.add_apf_audio_csr(platform)

        testSlave = wishbone.Interface()
        testRegion = SoCRegion(0x8000_0000, 0x10_0000, cached = False)
        
        self.bus.add_slave("test", testSlave, testRegion)

        # # testSlave.connect_to_pads

        # # For some reason this doesn't make the comb assignments itself?
        # # Master, because the internal wishbone is a slave, and the Verilog one is "master"
        self.comb += testSlave.connect_to_pads(platform.request("wishbone"), mode="master")

        test_master = wishbone.Interface()

        self.bus.add_master("test2", test_master)

        self.comb += test_master.connect_to_pads(platform.request("wishbone_master"), mode="slave")

    def add_controller_csr(self, platform: analogue_pocket.Platform):
        self.cont1_key = CSRStatus(size=32)

        cont1_key_pads = platform.request("cont1_key")
        self.comb += self.cont1_key.status.eq(cont1_key_pads)

    def add_apf_bridge_csr(self, platform: analogue_pocket.Platform):
        bridge_pins = platform.request("apf_bridge")

        self.bridge_request_read = CSR(1)
        self.comb += bridge_pins.request_read.eq(self.bridge_request_read.re)

        self.bridge_slot_id = CSRStorage(16)
        self.bridge_data_offset = CSRStorage(32)
        # self.bridge_local_address = CSRStorage(32)
        self.bridge_length = CSRStorage(32)
        self.ram_data_address = CSRStorage(32)

        self.bridge_file_size = CSRStatus(32)

        # Will go high when operation completes. Goes low after read
        self.bridge_status = CSRStatus(1)

        self.bridge_current_address = CSRStatus(32)

        self.prev_bridge_complete_trigger = Signal()

        self.sync += [
            self.prev_bridge_complete_trigger.eq(bridge_pins.complete_trigger),

            # Read clear must apply before write set, because otherwise you can miss a signal
            If(self.bridge_status.we,
                # Read, clear status
                self.bridge_status.status.eq(0)
            ),

            If(bridge_pins.complete_trigger & ~self.prev_bridge_complete_trigger,
                # Push status high
                self.bridge_status.status.eq(1)
            )
        ]

        self.comb += [
            bridge_pins.slot_id.eq(self.bridge_slot_id.storage),
            bridge_pins.data_offset.eq(self.bridge_data_offset.storage),
            # bridge_pins.local_address.eq(self.bridge_local_address.storage),
            bridge_pins.length.eq(self.bridge_length.storage),
            bridge_pins.ram_data_address.eq(self.ram_data_address.storage),

            self.bridge_file_size.status.eq(bridge_pins.file_size),

            self.bridge_current_address.status.eq(bridge_pins.current_address)
        ]

    def add_apf_audio_csr(self, platform: analogue_pocket.Platform):
        audio_pins = platform.request("apf_audio")

        self.audio_out = CSR(32)
        self.audio_playback_en = CSRStorage(1)
        self.audio_buffer_flush = CSR(1)

        self.audio_buffer_fill = CSRStatus(12)

        self.comb += [
            audio_pins.bus_out.eq(self.audio_out.r),
            audio_pins.bus_wr.eq(self.audio_out.re),

            audio_pins.playback_en.eq(self.audio_playback_en.storage),
            audio_pins.flush.eq(self.audio_buffer_flush.re),

            self.audio_buffer_fill.status.eq(audio_pins.buffer_fill)
        ]

# Build --------------------------------------------------------------------------------------------

def main():
    from litex.build.parser import LiteXArgumentParser
    import sys
    # LiteX directly reaches into sys.argv multiple times, so we have to inject all of our changed arguments at top level
    # Match up with Rust compiler target with FPU and RVC
    sys.argv.extend(["--cpu-type=vexriscv_smp", "--with-fpu", "--with-rvc", "--uart-baudrate=2000000", "--timer-uptime"])

    parser = LiteXArgumentParser(platform=analogue_pocket.Platform, description="LiteX SoC on Analog Pocket.")
    parser.add_target_argument("--sys-clk-freq", default=CLOCK_SPEED, type=float, help="System clock frequency.")
    args = parser.parse_args()

    soc_args = parser.soc_argdict

    soc = BaseSoC(
        sys_clk_freq = args.sys_clk_freq,
        **soc_args
    )
    builder_args = parser.builder_argdict
    builder_args["csr_svd"] = "pocket.svd"
    builder = Builder(soc, **builder_args)
    if args.build:
        builder.build(**parser.toolchain_argdict)

    if args.load:
        prog = soc.platform.create_programmer()
        prog.load_bitstream(builder.get_bitstream_filename(mode="sram").replace(".sof", ".rbf"))

if __name__ == "__main__":
    main()

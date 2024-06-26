from litex.build.altera.platform import AlteraPlatform
from litex.gen.fhdl.module import LiteXModule
from litex.soc.interconnect.csr import CSR, CSRStatus, CSRStorage
from migen.fhdl.structure import If, Signal

class APFAudio(LiteXModule):
    def __init__(self, platform: AlteraPlatform):
        audio_pins = platform.request("apf_audio")

        self.out = CSR(32)
        self.out.description = "The entrypoint to the audio buffer. Write two 16 bit signed values (for the left and right audio channels) here. This will push one value into the 4096 record FIFO that represents the audio buffer."
        self.playback_en = CSRStorage(1, description="Enable audio playback (reading of the audio buffer) when set to 1. No audio playback otherwise.")
        self.buffer_flush = CSR(1)
        self.buffer_flush.description = "Writing 1 to this register will immediately clear the audio buffer."

        self.buffer_fill = CSRStatus(12, description="The current fill level of the audio buffer. The buffer is full when set to `0xFFF`")

        self.comb += [
            audio_pins.bus_out.eq(self.out.r),
            audio_pins.bus_wr.eq(self.out.re),

            audio_pins.playback_en.eq(self.playback_en.storage),
            audio_pins.flush.eq(self.buffer_flush.re),

            self.buffer_fill.status.eq(audio_pins.buffer_fill)
        ]

class APFBridge(LiteXModule):
    def __init__(self, platform: AlteraPlatform):
        bridge_pins = platform.request("apf_bridge")

        self.request_read = CSR(1)
        self.request_read.description = "Writing 1 to this register will trigger a read request."
        self.comb += bridge_pins.request_read.eq(self.request_read.re)

        self.slot_id = CSRStorage(16, description="The slot ID defined in `data.json` for the desired asset/slot.")
        self.data_offset = CSRStorage(32, description="The offset from the start of the asset in the selected data slot to operate on.")
        # self.bridge_local_address = CSRStorage(32)
        self.transfer_length = CSRStorage(32, description="The length of data to transfer as part of this bridge operation. A length of `0xFFFFFFFF` will request the entire file (NOTE: As of Pocket firmware 1.1, this is bugged, and you just request the file size instead).")
        self.ram_data_address = CSRStorage(32, description="The address of RISC-V RAM to be manipulated in this operation. It is either the first write address for a read request, or the first read address for a write request.")

        self.file_size = CSRStatus(32, description="The file size on disk of the current selected asset in slot `bridge_slot_id`.")

        # Will go high when operation completes. Goes low after read
        self.status = CSRStatus(1, description="Indicates when the bridge is currently transferring a file. 1 when transferring, 0 otherwise. Clears its value on read.")

        self.current_address = CSRStatus(32, description="The current address the bridge is operating on. Can be used to show a progress bar/estimate time until completion.")

        self.prev_complete_trigger = Signal()

        self.sync += [
            self.prev_complete_trigger.eq(bridge_pins.complete_trigger),

            # Read clear must apply before write set, because otherwise you can miss a signal
            If(self.status.we,
                # Read, clear status
                self.status.status.eq(0)
            ),

            If(bridge_pins.complete_trigger & ~self.prev_complete_trigger,
                # Push status high
                self.status.status.eq(1)
            )
        ]

        self.comb += [
            bridge_pins.slot_id.eq(self.slot_id.storage),
            bridge_pins.data_offset.eq(self.data_offset.storage),
            # bridge_pins.local_address.eq(self.bridge_local_address.storage),
            bridge_pins.length.eq(self.transfer_length.storage),
            bridge_pins.ram_data_address.eq(self.ram_data_address.storage),

            self.file_size.status.eq(bridge_pins.file_size),

            self.current_address.status.eq(bridge_pins.current_address)
        ]

class APFID(LiteXModule):
    def __init__(self, platform: AlteraPlatform):
        id_pins = platform.request("apf_id")

        self.id = CSRStatus(64, description="The Cyclone V chip ID.")

        self.comb += [
            self.id.status.eq(id_pins.chip_id)
        ]

class APFInput(LiteXModule):
    def __init__(self, platform: AlteraPlatform):
        input_pins = platform.request("apf_input")

        self.cont1_key = CSRStatus(size=32, description="Controller 1 inputs. See docs.")
        self.cont2_key = CSRStatus(size=32, description="Controller 2 inputs. See docs.")
        self.cont3_key = CSRStatus(size=32, description="Controller 3 inputs. See docs.")
        self.cont4_key = CSRStatus(size=32, description="Controller 4 inputs. See docs.")

        self.comb += self.cont1_key.status.eq(input_pins.cont1_key)
        self.comb += self.cont2_key.status.eq(input_pins.cont2_key)
        self.comb += self.cont3_key.status.eq(input_pins.cont3_key)
        self.comb += self.cont4_key.status.eq(input_pins.cont4_key)

        self.cont1_joy = CSRStatus(size=32, description="Controller 1 joystick values. See docs.")
        self.cont2_joy = CSRStatus(size=32, description="Controller 2 joystick values. See docs.")
        self.cont3_joy = CSRStatus(size=32, description="Controller 3 joystick values. See docs.")
        self.cont4_joy = CSRStatus(size=32, description="Controller 4 joystick values. See docs.")

        self.comb += self.cont1_joy.status.eq(input_pins.cont1_joy)
        self.comb += self.cont2_joy.status.eq(input_pins.cont2_joy)
        self.comb += self.cont3_joy.status.eq(input_pins.cont3_joy)
        self.comb += self.cont4_joy.status.eq(input_pins.cont4_joy)

        self.cont1_trig = CSRStatus(size=32, description="Controller 1 trigger values. Values are binary on Pocket (`0 and 0xFFFF`), and analog on controllers with analog triggers. See docs.")
        self.cont2_trig = CSRStatus(size=32, description="Controller 2 trigger values. Values are binary on Pocket (`0 and 0xFFFF`), and analog on controllers with analog triggers. See docs.")
        self.cont3_trig = CSRStatus(size=32, description="Controller 3 trigger values. Values are binary on Pocket (`0 and 0xFFFF`), and analog on controllers with analog triggers. See docs.")
        self.cont4_trig = CSRStatus(size=32, description="Controller 4 trigger values. Values are binary on Pocket (`0 and 0xFFFF`), and analog on controllers with analog triggers. See docs.")

        self.comb += self.cont1_trig.status.eq(input_pins.cont1_trig)
        self.comb += self.cont2_trig.status.eq(input_pins.cont2_trig)
        self.comb += self.cont3_trig.status.eq(input_pins.cont3_trig)
        self.comb += self.cont4_trig.status.eq(input_pins.cont4_trig)

class APFRTC(LiteXModule):
    def __init__(self, platform: AlteraPlatform):
        rtc_pins = platform.request("apf_rtc")

        self.unix_seconds = CSRStatus(32, description="The current Pocket set time, from Unix epoch, in seconds.")
        self.date_bcd = CSRStatus(32, description="The launch Pocket set date, as BCD. NOT LIVE/INCREMENTING.")
        self.time_bcd = CSRStatus(32, description="The launch Pocket set time, as BCD. NOT LIVE/INCREMENTING.")

        self.comb += [
            self.unix_seconds.status.eq(rtc_pins.unix_seconds),
            self.date_bcd.status.eq(rtc_pins.date_bcd),
            self.time_bcd.status.eq(rtc_pins.time_bcd)
        ]

class APFVideo(LiteXModule):
    def __init__(self, soc):
        vblank = Signal()

        # 240 is what vactive is set to
        self.comb += If(soc.video_framebuffer_vtg.source.vcount >= 240,
                        vblank.eq(1)
                       ).Else(
                        vblank.eq(0)
                       )
        
        self.vsync_status = CSRStatus(1, description="Indicates when vsync occurs. Becomes 1 at vsync, and is set to 0 whenever read. If you read 1, vsync has occured between your two reads.")
        self.vblank_status = CSRStatus(1, description="1 when in vblank, 0 otherwise.")
        self.frame_counter = CSRStatus(32, description="Counts the number of frames displayed since startup. Comparing this value to a previous value can be used to track frame changes.")

        self.prev_vsync_trigger = Signal()

        self.sync += [
            self.prev_vsync_trigger.eq(soc.video_framebuffer_vtg.source.vsync),

            # Read clear must apply before write set, because otherwise you can miss a signal
            If(self.vsync_status.we,
                # Read, clear status
                self.vsync_status.status.eq(0)
            ),

            If(soc.video_framebuffer_vtg.source.vsync & ~self.prev_vsync_trigger,
                # Push status high
                self.vsync_status.status.eq(1),

                self.frame_counter.status.eq(self.frame_counter.status + 1)
            )
        ]

        self.comb += self.vblank_status.status.eq(vblank)

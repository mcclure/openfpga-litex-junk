//--------------------------------------------------------------------------------
// Auto-generated by LiteX (bf081324) on 2023-11-23 07:10:46
//--------------------------------------------------------------------------------
#ifndef __GENERATED_MEM_H
#define __GENERATED_MEM_H

#ifndef PLIC_BASE
#define PLIC_BASE 0xf0c00000L
#define PLIC_SIZE 0x00400000
#endif

#ifndef CLINT_BASE
#define CLINT_BASE 0xf0010000L
#define CLINT_SIZE 0x00010000
#endif

#ifndef ROM_BASE
#define ROM_BASE 0x00000000L
#define ROM_SIZE 0x00020000
#endif

#ifndef SRAM_BASE
#define SRAM_BASE 0x10000000L
#define SRAM_SIZE 0x00002000
#endif

#ifndef MAIN_RAM_BASE
#define MAIN_RAM_BASE 0x40000000L
#define MAIN_RAM_SIZE 0x04000000
#endif

#ifndef VIDEO_FRAMEBUFFER_BASE
#define VIDEO_FRAMEBUFFER_BASE 0x40c00000L
#define VIDEO_FRAMEBUFFER_SIZE 0x00800000
#endif

#ifndef EXAMPLE_SLAVE_BASE
#define EXAMPLE_SLAVE_BASE 0x80000000L
#define EXAMPLE_SLAVE_SIZE 0x00100000
#endif

#ifndef CSR_BASE
#define CSR_BASE 0xf0000000L
#define CSR_SIZE 0x00010000
#endif

#ifndef MEM_REGIONS
#define MEM_REGIONS "PLIC               0xf0c00000 0x400000 \nCLINT              0xf0010000 0x10000 \nROM                0x00000000 0x20000 \nSRAM               0x10000000 0x2000 \nMAIN_RAM           0x40000000 0x4000000 \nVIDEO_FRAMEBUFFER  0x40c00000 0x800000 \nEXAMPLE_SLAVE      0x80000000 0x100000 \nCSR                0xf0000000 0x10000 "
#endif
#endif
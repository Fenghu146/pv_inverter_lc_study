/*
 * 2837xD_FLASH_lnk_cpu1.cmd -- F28379D CPU1, program runs from FLASH
 *
 * Layout rationale:
 *   - codestart must sit at 0x000000 (boot-to-flash entry branch)
 *   - .text and .cinit get separate flash sectors so the linker never has
 *     to squeeze one around the other
 *   - RAMM1 holds the stack; its last 8 bytes are reserved for the flash
 *     prefetch errata, hence the 0x3F8 length and --stack_size=0x300
 *   - .bss/.data go into the large RAMGS blocks
 *
 * .TI.ramfunc is required by the compiler whenever --ramfunc=on or any
 * function carries __attribute__((ramfunc)). None of our code does, but
 * the C2000Ware device support source does reference it, so the section
 * must exist. It is placed in flash (no copy) because nothing in this
 * project executes a flash-write routine.
 */

MEMORY
{
PAGE 0 :  /* program */
   BEGIN            : origin = 0x000000, length = 0x000002
   RAMM0            : origin = 0x000122, length = 0x0002DE
   RAMLS0           : origin = 0x008000, length = 0x000800
   RESET            : origin = 0x3FFFC0, length = 0x000002
   FLASHA           : origin = 0x080002, length = 0x001FFE
   FLASHB           : origin = 0x082000, length = 0x002000
   FLASHC           : origin = 0x084000, length = 0x002000
   FLASHD           : origin = 0x086000, length = 0x002000
   FLASHE           : origin = 0x088000, length = 0x008000
   FLASHF           : origin = 0x090000, length = 0x008000
   FLASHG           : origin = 0x098000, length = 0x008000

PAGE 1 :  /* data */
   BOOT_RSVD        : origin = 0x000002, length = 0x000120
   RAMM1            : origin = 0x000400, length = 0x0003F8
   RAMLS1           : origin = 0x008800, length = 0x000800
   RAMLS2           : origin = 0x009000, length = 0x000800
   RAMLS3           : origin = 0x009800, length = 0x000800
   RAMLS4           : origin = 0x00A000, length = 0x000800
   RAMLS5           : origin = 0x00A800, length = 0x000800
   RAMGS0           : origin = 0x00C000, length = 0x001000
   RAMGS1           : origin = 0x00D000, length = 0x001000
   RAMGS2           : origin = 0x00E000, length = 0x001000
   RAMGS3           : origin = 0x00F000, length = 0x001000
}

SECTIONS
{
   /* ---- program ---- */
   codestart        : > BEGIN,      PAGE = 0
   .text            : >> FLASHE,    PAGE = 0, ALIGN(8)
   .cinit           : > FLASHC,     PAGE = 0, ALIGN(8)
   .pinit           : > FLASHC,     PAGE = 0, ALIGN(8)
   .switch          : > FLASHC,     PAGE = 0
   .init_array      : > FLASHC,     PAGE = 0, ALIGN(8)
   .TI.ramfunc      : > FLASHD,     PAGE = 0, ALIGN(8)

   /* constants live beside the code that reads them */
   .econst          : > FLASHB,     PAGE = 0, ALIGN(8)
   .const           : > FLASHB,     PAGE = 0, ALIGN(8)

   /* ---- data ---- */
   .stack           : > RAMM1,      PAGE = 1
   .ebss            : > RAMGS0,     PAGE = 1
   .bss             : > RAMGS0,     PAGE = 1
   .data            : > RAMGS1,     PAGE = 1
   .esysmem         : > RAMGS1,     PAGE = 1
   .sysmem          : > RAMGS1,     PAGE = 1
   .cio             : > RAMGS2,     PAGE = 1

   /* ---- reset vector ---- */
   .reset           : > RESET,      PAGE = 0, TYPE = DSECT
}
